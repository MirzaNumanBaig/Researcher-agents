"""Offline checks for agents/research_celebrities.py (no network): python3 -m unittest discover tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))
import research_celebrities as rc  # noqa: E402


def person(name, spouses=(), costars=(), directors=()):
    return {"name": name, "relationships": [{"name": n, "kind": "spouse", "start": "2010", "end": "", "ended_by": "", "fame": f} for n, f in spouses],
            "costars": [{"name": n, "projects": 2, "fame": f} for n, f in costars], "directors": [{"name": n, "projects": 3} for n in directors],
            "upcoming": [{"title": "Film X", "type": "film", "date": "2099-01-01", "directors": ["Dir A"]}], "recent": [],
            "family": {"children_recorded": 3, "adult_children_public": []}, "anime_voice_roles": [], "wikipedia_editions": 50}


class Research(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(rc.slug("Thorbjørn Harr"), "thorbj-rn-harr")

    def test_expansion_ranks_by_links_and_skips_tracked(self):
        people = [person("A", spouses=[("Spouse One", 40)], costars=[("Star Z", 80), ("B", 90)], directors=["Dir A"]),
                  person("B", costars=[("Star Z", 80)], directors=["Dir A", "Dir B"])]
        out = rc.expansion(people, ["A", "B"])
        names = [c["name"] for c in out]
        self.assertNotIn("B", names)
        self.assertEqual(names[:2], ["Star Z", "Dir A"])  # both link to 2 celebrities; the better-known one first
        z = next(c for c in out if c["name"] == "Star Z")
        self.assertEqual((z["links"], z["roles"]), (2, ["co-star"]))

    def test_report_never_names_minors_and_lists_upcoming(self):
        people = [person("A", spouses=[("Spouse One", 40)])]
        text = rc.report(people, rc.expansion(people, ["A"]))
        self.assertIn("Film X", text)
        self.assertIn("3 child(ren) recorded", text)
        self.assertIn("Spouse One", text)


if __name__ == "__main__":
    unittest.main()
