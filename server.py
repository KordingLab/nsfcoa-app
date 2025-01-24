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


@app.get("/scholarlike")
async def scholarlike():
    return fastapi.responses.HTMLResponse(open("scholarlike.html").read())


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
    authorships = [auth for work in works for auth in work["authorships"]]
    # Set unique on author['id']:
    authorships = [auth for auth in authorships]

    collaborators = []
    for author in authorships:
        name = (
            author["author"]["display_name"]
            if isinstance(author, dict) and "author" in author
            else "Unknown"
        )
        inst = (
            author["institutions"]
            if isinstance(author, dict) and "institutions" in author
            else []
        )
        inst = inst[0]["display_name"] if inst else None
        if inst is None:
            try:
                insts = get_insts(author.get("author", {}).get("id", "").split("/")[-1])
                if insts:
                    inst = insts[0]["institution"]["display_name"]
            except:
                inst = ""
        if inst is None:
            continue

        name_split = name.split()
        if len(name_split) == 3:
            first, middle, last = name_split
        elif len(name_split) == 2:
            first, last = name_split
            middle = None
        elif len(name_split) == 4:
            first, middle = name_split[:2]
            last = " ".join(name_split[2:])

        collaborators.append(
            {
                "first": first,
                "middle": middle or "",
                "last": last,
                "institution": inst,
            }
        )

    collaborators = sorted(collaborators, key=lambda x: (x["institution"], x["last"]))

    return {"collaborators": collaborators}
