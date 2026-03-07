"""
Citation Enrichment — Populate references.bib with all citations from:
1. Source PDFs (bias_mitigation.pdf, Bias Auditing Framework.pdf, Bias Detection findings.pdf)
2. Semantic Scholar search (bias in financial AI, EU AI Act, fairness metrics, fraud detection)
3. DOIs cited in the paper

Resolves DOIs via Crossref API. Outputs IEEE-style BibTeX to references.bib.
"""

import json
import os
import re
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")
PAPER_DIR = os.path.join(OUTPUT_DIR, "paper")
BIB_PATH = os.path.join(PAPER_DIR, "references.bib")

# DOIs from source documents (paper_draft References section)
SOURCE_DOIS = [
    "10.3390/bdcc7010015",   # Pagano et al. - Bias and unfairness in ML
    "10.9781/ijimai.2023.11.001",
    "10.24294/jipd11489",
    "10.48550/arXiv.2305.05862",
    "10.1016/j.sciaf.2024.e02281",
    "10.51594/csitrj.v3i3.1559",
    "10.3390/sci6010003",
    "10.37547/tajet/Volume07Issue05-19",
]

# Semantic Scholar search queries for relevant literature
SEMANTIC_QUERIES = [
    "bias mitigation financial AI credit scoring",
    "EU AI Act fairness thresholds algorithmic",
    "equalized odds demographic parity fraud detection",
    "SMOTE fairness imbalanced classification",
    "disparate impact machine learning",
    "bias auditing lifecycle AI systems",
    "threshold adjustment post-processing fairness",
    "ExponentiatedGradient Fairlearn fairness",
]


def _bib_key_from_author_year(authors: list, year: str) -> str:
    """Generate BibTeX key: firstauthor2024."""
    if not authors or not year:
        return "unknown" + str(hash(str(authors) + year))[:6]
    first = authors[0].get("family", authors[0].get("name", "unknown"))
    if isinstance(first, dict):
        first = first.get("family", first.get("name", "unknown"))
    # Sanitize: lowercase, alphanumeric only
    key = re.sub(r"[^a-z0-9]", "", str(first).lower())[:20] + year
    return key


def _crossref_to_bibtex(doi: str) -> str | None:
    """Resolve DOI via Crossref API, return BibTeX entry or None."""
    try:
        import httpx
    except ImportError:
        return None
    url = f"https://api.crossref.org/works/{doi}/transform/application/x-bibtex"
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url)
            if r.status_code == 200 and r.text.strip():
                return r.text.strip()
    except Exception:
        pass
    return None


def _semantic_scholar_to_bibtex(paper: dict) -> str:
    """Convert Semantic Scholar paper dict to BibTeX entry."""
    title = paper.get("title", "Unknown").replace("{", "{{").replace("}", "}}")
    authors = paper.get("authors", [])
    year = str(paper.get("year", ""))
    venue = (paper.get("venue", "") or paper.get("journal", "") or "").replace("{", "{{").replace("}", "}}")
    arxiv_id = paper.get("arxivId", "") or paper.get("arxiv_id", "")

    if isinstance(authors, list) and authors:
        names = []
        for a in authors[:8]:
            n = a.get("name", "") if isinstance(a, dict) else getattr(a, "name", str(a))
            if n:
                parts = n.split()
                names.append(f"{parts[-1]}, {'. '.join(p[0] for p in parts[:-1])}." if len(parts) >= 2 else n)
        auth_str = " and ".join(names) if len(names) <= 3 else " and ".join(names[:3]) + " and others"
    else:
        auth_str = "Unknown"

    first_author = (authors or [{}])[0]
    fam = first_author.get("name", "").split()[-1] if isinstance(first_author, dict) else "paper"
    key = re.sub(r"[^a-z0-9]", "", (str(fam) + year).lower())[:25] or "paper"

    if arxiv_id or "arxiv" in venue.lower():
        return f"""@article{{{key},
  author = {{{auth_str}}},
  title = {{{title}}},
  journal = {{arXiv preprint arXiv:{arxiv_id or 'unknown'}}},
  year = {{{year}}}
}}"""
    if venue:
        return f"""@inproceedings{{{key},
  author = {{{auth_str}}},
  title = {{{title}}},
  booktitle = {{{venue}}},
  year = {{{year}}}
}}"""
    return f"""@article{{{key},
  author = {{{auth_str}}},
  title = {{{title}}},
  year = {{{year}}}
}}"""


def resolve_dois(dois: list[str]) -> list[tuple[str, str]]:
    """Resolve DOIs to BibTeX. Returns [(doi, bibtex), ...]."""
    results = []
    for doi in dois:
        bib = _crossref_to_bibtex(doi)
        if bib:
            # Extract key for dedup
            m = re.search(r"@\w+\{([^,]+),", bib)
            key = m.group(1).strip() if m else doi.replace("/", "_").replace(".", "_")
            results.append((doi, bib))
        time.sleep(0.5)  # Rate limit
    return results


def search_semantic_scholar(queries: list[str], limit_per_query: int = 5) -> list[dict]:
    """Search Semantic Scholar for papers. Returns list of paper dicts."""
    try:
        from semanticscholar import SemanticScholar
    except ImportError:
        return []

    all_papers = []
    seen_titles = set()
    sch = SemanticScholar()
    fields = ["title", "authors", "year", "venue", "paperId", "externalIds"]

    for q in queries:
        try:
            resp = sch.search_paper(q, limit=limit_per_query, fields=fields)
            items = getattr(resp, "data", None) or resp
            if not isinstance(items, (list, tuple)):
                items = list(items) if items else []
            for p in items:
                if p is None:
                    continue
                title = (getattr(p, "title", "") or "").strip()
                if not title or title.lower() in seen_titles:
                    continue
                seen_titles.add(title.lower())
                authors = []
                for a in (getattr(p, "authors", None) or []):
                    if hasattr(a, "name"):
                        authors.append({"name": a.name})
                    elif isinstance(a, dict):
                        authors.append({"name": a.get("name", "")})
                ext = getattr(p, "externalIds", None) or {}
                arxiv_id = ""
                if isinstance(ext, dict):
                    arxiv_id = ext.get("ArXiv", "") or ext.get("arXiv", "")
                elif hasattr(ext, "get"):
                    arxiv_id = ext.get("ArXiv", "") or ""
                paper = {
                    "title": title,
                    "authors": authors,
                    "year": str(getattr(p, "year", "") or ""),
                    "venue": getattr(p, "venue", "") or "",
                    "paperId": getattr(p, "paperId", "") or "",
                    "arxiv_id": arxiv_id,
                }
                all_papers.append(paper)
        except Exception:
            pass
        time.sleep(0.5)
    return all_papers


def get_pdf_citations() -> list[dict]:
    """Get citations from source PDFs (author-year and DOIs)."""
    try:
        from pdf_source_extractor import get_all_citations
        return get_all_citations()
    except ImportError:
        return []


def main():
    os.makedirs(PAPER_DIR, exist_ok=True)

    entries = {}  # key -> bibtex
    keys_seen = set()

    # 1. Core static refs (already in paper)
    core_bib = r"""@article{huang2025,
  author  = {Huang, C. and Turetken, O.},
  title   = {Bias mitigation in AI-based credit scoring: A comparative analysis of pre-, in-, and post-processing techniques},
  journal = {Journal of Artificial Intelligence Research},
  year    = {2025}
}

@article{ntoutsi2020,
  author  = {Ntoutsi, E. and Fafalios, P. and Gadiraju, U. and Iosifidis, V. and Nejdl, W. and Vidal, M.-E. and Ruggieri, S. and Turini, F. and Papadopoulos, S. and Krasanakis, E. and others},
  title   = {Bias in data-driven artificial intelligence systems --- An introductory survey},
  journal = {WIREs Data Mining and Knowledge Discovery},
  volume  = {10},
  number  = {3},
  pages   = {e1356},
  year    = {2020}
}

@article{pagano2023,
  author  = {Pagano, T. P. and Loureiro, R. B. and Lisboa, F. V. N. and Paquevich, R. M. and Guimarães, L. N. F. and others},
  title   = {Bias and unfairness in machine learning models: A systematic review on datasets, tools, fairness metrics, and identification and mitigation methods},
  journal = {Big Data and Cognitive Computing},
  volume  = {7},
  number  = {1},
  pages   = {15},
  year    = {2023}
}

@misc{euai2024,
  author       = {{European Parliament and Council of the European Union}},
  title        = {Regulation (EU) 2024/1689 laying down harmonised rules on artificial intelligence (Artificial Intelligence Act)},
  howpublished = {Official Journal of the European Union, L series},
  year         = {2024}
}

@misc{mlgulb2018,
  author       = {{Machine Learning Group --- ULB}},
  title        = {Credit Card Fraud Detection},
  howpublished = {Kaggle Dataset},
  year         = {2018},
  url          = {https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud}
}

@article{murikah2024,
  author  = {Murikah, W. and Nthenge, J. and Musyoka, F.},
  title   = {Bias and ethics of AI systems applied in auditing --- A systematic review},
  journal = {arXiv},
  year    = {2024}
}

@article{gonzalez2023,
  author  = {González-Sendino, O. and others},
  title   = {Bias audit frameworks --- Legal and socio-technical perspectives},
  journal = {arXiv},
  year    = {2023}
}

@article{chen2023,
  author  = {Chen, Z. and others},
  title   = {Temporal bias and distribution shift in machine learning},
  journal = {arXiv},
  year    = {2023}
}

@article{funda2025,
  author  = {Funda, A. and others},
  title   = {Intersectional fairness and affected communities in AI auditing},
  journal = {arXiv},
  year    = {2025}
}
"""
    for m in re.finditer(r"@(\w+)\{([^,]+),\s*([\s\S]*?)(?=\n\n@|\Z)", core_bib):
        typ, key, body = m.group(1), m.group(2).strip(), m.group(3).strip().rstrip("}")
        entries[key] = f"@{typ}{{{key},\n  {body}\n}}"
        keys_seen.add(key.lower())

    # 2. Resolve DOIs from source documents (skip DOIs we already have)
    skip_dois = {"10.3390/bdcc7010015"}  # = pagano2023
    print("  Resolving DOIs via Crossref...")
    for doi, bib in resolve_dois(SOURCE_DOIS):
        if doi in skip_dois:
            continue
        m = re.search(r"@\w+\{([^,]+),", bib)
        raw_key = m.group(1).strip() if m else ""
        key = raw_key if raw_key and len(raw_key) > 3 and raw_key not in keys_seen else "doi_" + doi.replace("/", "_").replace(".", "_")[:30]
        key_lower = key.lower()
        if key_lower not in keys_seen:
            keys_seen.add(key_lower)
            if key != raw_key and m:
                bib = bib.replace(raw_key, key, 1)
            entries[key] = bib.rstrip()

    # 3. Semantic Scholar search
    print("  Searching Semantic Scholar...")
    papers = search_semantic_scholar(SEMANTIC_QUERIES, limit_per_query=4)
    for p in papers:
        bib = _semantic_scholar_to_bibtex(p)
        m = re.search(r"@\w+\{([^,]+),", bib)
        key = m.group(1).strip() if m else "paper"
        key_lower = key.lower()
        if key_lower not in keys_seen:
            keys_seen.add(key_lower)
            entries[key] = bib

    # Write references.bib
    out = []
    for k, v in sorted(entries.items(), key=lambda x: x[0].lower()):
        out.append(v)
        out.append("")
    content = "\n".join(out)
    with open(BIB_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Wrote {len(entries)} entries to {BIB_PATH}")
    return BIB_PATH


if __name__ == "__main__":
    print("=" * 60)
    print("  CITATION ENRICHMENT — Populate references.bib")
    print("=" * 60)
    main()
