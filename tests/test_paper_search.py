import sys
import unittest
import json
import io
import urllib.error
from contextlib import redirect_stdout
from unittest import mock
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "tools" / "paper_search" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from anysearch_academic import AnySearchAcademic
from hybrid_scholar import HybridPaper, HybridScholar
from openalex_scholar import Paper
from openalex_scholar import OpenAlexScholar
from provider_result import ProviderResult
from openalex_scholar import main as openalex_main


class ProviderOutcomeTests(unittest.TestCase):
    def test_network_failure_is_not_a_successful_empty_search(self):
        provider = OpenAlexScholar()
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            result = provider.search_result("test")
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.error["kind"], "network")
            self.assertEqual(provider.search_papers("test"), [])
            self.assertEqual(provider.last_result.status, "failed")
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"results": []}'
        with mock.patch("urllib.request.urlopen", return_value=response):
            self.assertEqual(provider.search_result("test").status, "empty")

    def test_anysearch_rpc_and_schema_errors_are_failed(self):
        provider = AnySearchAcademic()
        for payload, error_kind in [
            ({"error": {"code": -32000, "message": "redacted"}}, "rpc"),
            ({"result": {"isError": True, "content": []}}, "tool_error"),
            ({"result": {"content": [{"type": "text", "text": "service unavailable"}]}}, "unrecognized_response"),
        ]:
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
            with mock.patch("urllib.request.urlopen", return_value=response):
                result = provider.search_result("test")
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.error["kind"], error_kind)

    def test_partial_service_failure_remains_visible_with_valid_results(self):
        scholar = HybridScholar()
        paper = Paper("AHP", ["A"], 2020, 0, None, None)
        with mock.patch.object(scholar.openalex, "search_result", return_value=ProviderResult("openalex", "ok", [paper])), \
             mock.patch.object(scholar.anysearch, "search_result", return_value=ProviderResult("anysearch", "failed", error={"kind": "http", "code": 503})):
            result = scholar.search_papers("AHP")
        self.assertEqual(result["search_status"], "partial")
        self.assertEqual(result["providers"]["anysearch"]["status"], "failed")
        self.assertEqual(len(result["openalex_only"]), 1)

    def test_matching_metadata_never_asserts_original_text_support(self):
        paper = HybridPaper("Example", [], 2020, 0, None, None,
                            sources=["openalex", "anysearch"])
        payload = paper.to_dict()
        self.assertTrue(payload["cross_validated"])
        self.assertTrue(payload["metadata_matched"])
        self.assertEqual(payload["claim_support"], "unverified")

    def test_standalone_json_reports_failure_without_empty_search_claim(self):
        output = io.StringIO()
        failure = ProviderResult("openalex", "failed", error={"kind": "network"})
        with mock.patch.object(sys, "argv", ["openalex_scholar.py", "--query", "AHP", "--json"]), \
             mock.patch.object(OpenAlexScholar, "search_result", return_value=failure), redirect_stdout(output):
            exit_code = openalex_main()
        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["papers"], [])

    def test_explicit_anysearch_empty_response_is_successful(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "result": {"content": [{"type": "text", "text": "## Search Results (0 results)"}]}
        }).encode()
        with mock.patch("urllib.request.urlopen", return_value=response):
            result = AnySearchAcademic().search_result("test")
        self.assertEqual(result.status, "empty")
        self.assertIsNone(result.error)

    def test_all_failed_hybrid_search_is_visible(self):
        scholar = HybridScholar()
        with mock.patch.object(scholar.openalex, "search_result", return_value=ProviderResult("openalex", "failed", error={"kind": "network"})), \
             mock.patch.object(scholar.anysearch, "search_result", return_value=ProviderResult("anysearch", "failed", error={"kind": "network"})):
            result = scholar.search_papers("AHP")
        self.assertEqual(result["search_status"], "failed")
        self.assertEqual(len(result["providers"]), 2)


class AnySearchParserTests(unittest.TestCase):
    def test_parses_markdown_mcp_response(self):
        response = {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": """## Search Results (1 results)\n\n### 1. The Analytic Hierarchy Process\n- **URL**: https://doi.org/10.1016/0377-2217(85)90273-7\n- **Authors**: Thomas L. Saaty, Kevin P. Kearns\n- **Published**: 1985\n- **Citations**: 15444\n""",
                    }
                ]
            }
        }

        papers = AnySearchAcademic()._parse_response(response)

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["title"], "The Analytic Hierarchy Process")
        self.assertEqual(papers[0]["doi"], "10.1016/0377-2217(85)90273-7")
        self.assertEqual(papers[0]["authors"], ["Thomas L. Saaty", "Kevin P. Kearns"])
        self.assertEqual(papers[0]["year"], 1985)
        self.assertEqual(papers[0]["citations"], 15444)


class OpenAlexMetadataTests(unittest.TestCase):
    def test_extracts_venue_volume_issue_pages_and_url(self):
        data = {
            "results": [
                {
                    "display_name": "A paper",
                    "authorships": [{"author": {"display_name": "A. Author"}}],
                    "publication_year": 2024,
                    "cited_by_count": 3,
                    "doi": "https://doi.org/10.1000/example",
                    "abstract_inverted_index": None,
                    "biblio": {"volume": "12", "issue": "3", "first_page": "10", "last_page": "20"},
                    "primary_location": {
                        "landing_page_url": "https://publisher.example/paper",
                        "source": {"display_name": "Journal of Examples"},
                    },
                }
            ]
        }

        paper = OpenAlexScholar()._parse_results(data)[0]

        self.assertEqual(paper.venue, "Journal of Examples")
        self.assertEqual(paper.volume, "12")
        self.assertEqual(paper.issue, "3")
        self.assertEqual(paper.pages, "10-20")
        self.assertEqual(paper.url, "https://publisher.example/paper")


class FusionTests(unittest.TestCase):
    def setUp(self):
        self.scholar = HybridScholar()
        self.scholar._current_query = "AHP"

    def test_title_match_without_doi_becomes_cross_validated(self):
        oa = [
            Paper(
                title="The Analytic Hierarchy Process",
                authors=["Thomas L. Saaty"],
                publication_year=1985,
                cited_by_count=100,
                doi=None,
                abstract=None,
            )
        ]
        anysearch = [
            {
                "title": "The analytic hierarchy process",
                "authors": ["Thomas L. Saaty"],
                "year": 1985,
                "citations": 90,
                "doi": None,
                "abstract": None,
            }
        ]

        result = self.scholar._fuse(oa, anysearch, final_limit=1)

        self.assertEqual(len(result["cross_validated"]), 1)
        self.assertEqual(result["cross_validated"][0].sources, ["openalex", "anysearch"])

    def test_single_engine_respects_requested_limit(self):
        oa = [
            Paper(f"Paper {i}", ["A"], 2020, 10 - i, None, None)
            for i in range(5)
        ]

        result = self.scholar._fuse(oa, [], final_limit=1)

        total = sum(
            len(result[key])
            for key in ("cross_validated", "openalex_only", "anysearch_only")
        )
        self.assertEqual(total, 1)

    def test_title_match_works_when_only_one_engine_has_doi(self):
        oa = [Paper("A Reliable Model", ["A"], 2022, 5, "10.1000/model", None)]
        anysearch = [{
            "title": "A reliable model",
            "authors": ["A"],
            "year": 2022,
            "citations": 4,
            "doi": None,
            "abstract": None,
        }]

        result = self.scholar._fuse(oa, anysearch, final_limit=1)

        self.assertEqual(result["cross_validated"][0].doi, "10.1000/model")

    def test_specialist_query_filters_topically_unrelated_high_citation_results(self):
        self.scholar._current_query = "Sellmeier 4H-SiC Fabry-Perot"
        oa = [
            Paper(
                "Graphene electro-optic modulation",
                ["A"], 2024, 5000, "10.1000/graphene", "Lithium niobate devices.",
            ),
            Paper(
                "Sellmeier dispersion and Fabry-Perot interference in 4H-SiC",
                ["B"], 2023, 10, "10.1000/sic", "Optical constants of silicon carbide.",
            ),
        ]

        result = self.scholar._fuse(oa, [], final_limit=5)
        selected = result["openalex_only"]

        self.assertEqual([paper.doi for paper in selected], ["10.1000/sic"])
        self.assertEqual(result["stats"]["filtered_irrelevant"], 1)

    def test_specialist_query_keeps_partial_match_when_metadata_has_no_abstract(self):
        self.scholar._current_query = "Sellmeier 4H-SiC Fabry-Perot"
        anysearch = [{
            "title": "Temperature dependence of the thermo-optic coefficient in 4H-SiC",
            "authors": [],
            "year": 2022,
            "citations": 0,
            "doi": "10.1000/partial",
            "abstract": None,
        }]

        result = self.scholar._fuse([], anysearch, final_limit=5)

        self.assertEqual([paper.doi for paper in result["anysearch_only"]], ["10.1000/partial"])

    def test_same_engine_duplicate_titles_with_different_dois_are_collapsed(self):
        self.scholar._current_query = "4H-SiC thermo-optic"
        anysearch = [
            {
                "title": "Temperature dependence of the thermo-optic coefficient in 4H-SiC",
                "authors": [], "year": 2022, "citations": 4,
                "doi": "10.1000/final", "abstract": None,
            },
            {
                "title": "Temperature Dependence of the Thermo Optic Coefficient in 4H SiC",
                "authors": [], "year": 2021, "citations": 0,
                "doi": "10.1000/preprint", "abstract": None,
            },
        ]

        result = self.scholar._fuse([], anysearch, final_limit=5)

        self.assertEqual([paper.doi for paper in result["anysearch_only"]], ["10.1000/final"])
        self.assertEqual(result["stats"]["collapsed_duplicates"], 1)


if __name__ == "__main__":
    unittest.main()
