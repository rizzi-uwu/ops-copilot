"""Run the meeting reader on all sample transcripts and score it against hand labels.

Needs an API key (DEEPSEEK_API_KEY or ANTHROPIC_API_KEY). This produces the numbers you quote.

Two sets, reported separately
  basic  meetings 1-5: clear phrasing ("I'll do X by Friday")
  hard   meetings 6-10: corrections and retracted commitments, vague or relative dates,
         implicit assignments, German and mixed German/English, hypotheticals that are not
         commitments, a meeting with no decisions

Scores
  action recall     share of labelled action items found with the right owner, and the right
                    deadline where the transcript gives one clear date
  action precision  share of extracted action items that match a label
  decisions, risks  whether the count matches the label

The wording of items is not scored, so also read a few outputs by hand and say so when you report.
Labels live in data/expected.json (written by src/make_data.py from my reading of the transcripts).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm
import meeting_reader as mr
import scoring

DATA = Path(__file__).resolve().parent.parent / "data"

if not llm.has_key():
    sys.exit(llm.MISSING_KEY_MESSAGE)
print(f"Provider: {llm.provider()}, model: {llm.model_name()}\n")

expected = json.loads((DATA / "expected.json").read_text())["meetings"]
sets = {}
details = []

print(f"{'meeting':30} {'set':6} {'actions':>11} {'decisions':>10} {'risks':>6}")
for name, exp in expected.items():
    text = (DATA / "transcripts" / f"{name}.txt").read_text(encoding="utf-8")
    got = mr.read_meeting(text)
    s = scoring.score_actions(exp["action_labels"], got["action_items"])
    d_ok = len(got["decisions"]) == exp["decisions"]
    r_ok = len(got["unowned_risks"]) == exp["risks"]
    st = sets.setdefault(exp["set"], dict(matched=0, expected=0, extracted=0, dec=0, risk=0, n=0))
    st["matched"] += s["matched"]
    st["expected"] += s["expected"]
    st["extracted"] += s["extracted"]
    st["dec"] += d_ok
    st["risk"] += r_ok
    st["n"] += 1
    print(f"{name:30} {exp['set']:6} {s['matched']}/{s['expected']} of {s['extracted']:>2} "
          f"{'ok' if d_ok else 'XX':>9} {'ok' if r_ok else 'XX':>6}")
    if s["missed"] or s["extra"] or not d_ok or not r_ok:
        details.append((name, exp, got, s, d_ok, r_ok))


def summary(label, st):
    rec = 100 * st["matched"] / max(st["expected"], 1)
    prec = 100 * st["matched"] / max(st["extracted"], 1)
    print(f"{label:6} actions: {st['matched']}/{st['expected']} found ({rec:.0f}% recall), "
          f"{st['matched']}/{st['extracted']} extracted match ({prec:.0f}% precision) | "
          f"decisions right in {st['dec']}/{st['n']} meetings | risks right in {st['risk']}/{st['n']} meetings")


print()
for set_name in ("basic", "hard"):
    if set_name in sets:
        summary(set_name, sets[set_name])
total = {k: sum(st[k] for st in sets.values()) for k in ("matched", "expected", "extracted", "dec", "risk", "n")}
summary("all", total)

if details:
    print("\nMismatches to look at:")
    for name, exp, got, s, d_ok, r_ok in details:
        for m in s["missed"]:
            print(f"  {name}: missed label {m['owner']} / {m['deadline']}")
        for e in s["extra"]:
            print(f"  {name}: extra item {e.get('owner')} / {e.get('deadline')} / {e.get('task')}")
        if not d_ok:
            print(f"  {name}: decisions expected {exp['decisions']}, got {len(got['decisions'])}: "
                  + "; ".join(d["decision"] for d in got["decisions"]))
        if not r_ok:
            print(f"  {name}: risks expected {exp['risks']}, got {len(got['unowned_risks'])}: "
                  + "; ".join(r["risk"] for r in got["unowned_risks"]))
