import re
import fastapi
from openalex import OpenAlex
import datetime
from functools import cache
import os


def get_mailto():
    return os.environ.get("OPENALEX_MAILTO", "default@example.com")


def is_orcid(identifier):
    return re.match(r"^(\d{4}-){3}\d{3}(\d|X)$", identifier) is not None


def split_name(name):
    name_split = name.split()

    if not name_split:
        return "Unknown", "", ""
    if len(name_split) == 1:
        return name_split[0], "", ""
    if len(name_split) == 2:
        first, last = name_split
        return first, "", last
    if len(name_split) == 3:
        first, middle, last = name_split
        return first, middle, last
    if len(name_split) == 4:
        first, middle = name_split[:2]
        last = " ".join(name_split[2:])
        return first, middle, last

    return name_split[0], " ".join(name_split[1:-1]), name_split[-1]


def get_publication_year(publication_date):
    match = re.match(r"^(\d{4})", publication_date or "")
    return match.group(1) if match else ""


app = fastapi.FastAPI()


@app.get("/")
def read_root():
    return {"status": "ok"}


@cache
def get_insts(auth_id):
    oa = OpenAlex(mailto=get_mailto())
    return oa.get_author_institutions(auth_id)


@app.get("/nsf-coa")
async def render_nsf_template():
    return fastapi.responses.HTMLResponse(open("nsf-coa.html").read())


@app.get("/search")
async def render_author_search():
    return fastapi.responses.HTMLResponse(open("author_search.html").read())


@app.get("/scholarlike")
async def scholarlike():
    return fastapi.responses.HTMLResponse(open("scholarlike.html").read())


@app.get("/search-authors")
async def search_authors(name: str):
    """
    Search for authors by name
    """
    oa = OpenAlex(mailto=get_mailto())
    authors = oa.get_authors(filter={"display_name.search": name})
    return {
        "authors": [
            {
                "name": author.get("display_name", "Unknown Author"),
                "affiliations": [
                    affil.get(
                        "institution", {"display_name": "Unknown Institution"}
                    ).get("display_name", "Unknown Affiliation")
                    for affil in author.get("affiliations", [])
                ],
                "orcid": (
                    author.get("orcid", "/Unknown-ORCID") or "/Unknown-ORCID"
                ).split("/")[-1],
            }
            for author in authors
        ]
    }


@app.get("/author-by-orcid")
async def get_author_by_orcid(orcid: str):
    """
    Get author details and their papers by ORCID
    """
    oa = OpenAlex(mailto=get_mailto())
    if not is_orcid(orcid):
        return {"error": "Invalid ORCID format"}

    author_id = oa.get_author_uri_by_orcid(orcid)
    author_details = oa.get_authors(filter={"id": author_id})[0]
    works = oa.get_works(filter={"authorships.author.id": author_id}) or []

    papers = []
    for work in works:
        papers.append(
            {
                "title": work.get("title", "Unknown Title"),
                "authors": [
                    authorship["author"]["display_name"]
                    for authorship in work.get("authorships", [])
                ],
                "publication_date": work.get("publication_date", "Unknown Date"),
                "citation_count": work.get("cited_by_count", 0),
                "counts_by_year": {
                    v["year"]: v["cited_by_count"]
                    for v in work.get("counts_by_year", {})
                },
            }
        )

    return {
        "author": {
            "name": author_details.get("display_name", "Unknown Author"),
            "orcid": orcid,
            "affiliations": author_details.get("affiliations", []),
        },
        "papers": papers,
    }


@app.get("/nsf-coa-lookup")
async def get_nsf_coa(author: str, months: int = 48):
    """
    Get a list of collaborators + affils from the last N months for a given author
    """
    oa = OpenAlex(mailto=get_mailto())
    if is_orcid(author):
        author_id = oa.get_author_uri_by_orcid(author)
    else:
        author_id = oa.get_author_uri_by_search(author)
    n_months_ago_str = (
        datetime.datetime.now() - datetime.timedelta(days=30 * months)
    ).strftime("%Y-%m-%d")
    works = oa.get_works(
        filter={
            "authorships.author.id": author_id,
            "publication_date": f">{n_months_ago_str}",
        }
    )
    collaborator_lookup = {}
    for work in works:
        publication_date = work.get("publication_date") or ""
        for authorship in work.get("authorships", []):
            collaborator = authorship.get("author", {})
            collaborator_id = collaborator.get("id")
            if not collaborator_id or collaborator_id == author_id:
                continue

            existing = collaborator_lookup.get(collaborator_id)
            if existing is None:
                collaborator_lookup[collaborator_id] = {
                    "author": collaborator,
                    "institutions": authorship.get("institutions", []),
                    "last_interaction_date": publication_date,
                }
                continue

            if authorship.get("institutions") and not existing["institutions"]:
                existing["institutions"] = authorship["institutions"]

            if publication_date > existing["last_interaction_date"]:
                existing["last_interaction_date"] = publication_date

    collaborators = []
    for collaborator in collaborator_lookup.values():
        name = (
            collaborator["author"]["display_name"]
            if isinstance(collaborator, dict) and "author" in collaborator
            else "Unknown"
        )
        inst = (
            collaborator["institutions"]
            if isinstance(collaborator, dict) and "institutions" in collaborator
            else []
        )
        inst = inst[0]["display_name"] if inst else None
        if inst is None:
            try:
                insts = get_insts(
                    collaborator.get("author", {}).get("id", "").split("/")[-1]
                )
                if insts:
                    inst = insts[0]["institution"]["display_name"]
            except Exception:
                inst = ""
        if inst is None:
            continue

        first, middle, last = split_name(name)

        collaborators.append(
            {
                "first": first,
                "middle": middle or "",
                "last": last,
                "institution": inst,
                "last_interaction_year": get_publication_year(
                    collaborator["last_interaction_date"]
                ),
            }
        )

    collaborators = sorted(collaborators, key=lambda x: (x["institution"], x["last"]))

    return {"collaborators": collaborators}
