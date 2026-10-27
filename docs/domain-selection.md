# Launch Runbook

## Studio name decision

**Decision: we are going with `heronbench.com` (Heron Bench).**

This is conditional on the social handles being available and there being no trademark conflict. Both checks were run on 2026-10-27 and nothing blocking was found (details below). The next step is to actually register the domain and handles.

## Domain name review

The candidates were assessed for how well they evoke a software studio.

"Bench" (as in workbench) suggests a place where things are made by hand: craft and a small maker's shop. The first word is a natural noun and nothing in the set says "software" on its own, so the name needs a tagline or a `.dev` / `.studio` context to carry the meaning.

Problems with "bench" itself:

- It also means benchmark, which skews toward performance-testing tools.
- In IT consulting, "the bench" is where staff wait between projects.
- It is a generic suffix, so the first word has to carry the brand.

### Ranking

| # | Domain | Pros | Cons |
|---|--------|------|------|
| 1 | heronbench.com | Heron suggests patient, precise, calm craft. Flows well aloud. Familiar bird in Australia. Easy to spell. | Slightly soft or lyrical for a hard-edged studio. 10 letters. |
| 2 | larchbench.com | Most coherent story: larch is tough, rot-resistant timber, so a bench made of good wood. Distinctive. | Repeated "ch" sound is tongue-twisty. Larch is a northern-hemisphere conifer many Australians won't picture. Can be misheard as "lurch". |
| 3 | oxbench.com | Shortest (7 letters), strong, memorable. Ox means a reliable workhorse. | Reads a bit like gym equipment. "Ox" is a crowded prefix in tech. Slow, agricultural connotations. |
| 4 | tealbench.com | Clean to say and spell. Teal is a colour and a duck. Easy visual identity. | Very common, trendy brand word. Colour-first names feel generic. |
| 5 | kestrelbench.com | Kestrel suggests precision and sharp eyesight. Strong imagery. | 12 letters. Easy to misspell. Heavy to say and type. |
| 6 | basaltbench.com | Solid, dependable, industrial. Fits a "built to last" pitch. | Cold and heavy. Sounds like "base salt". 11 letters. Basalt is already a common tech name. |
| 7 | finchbench.com | Short, cute, bird motif. | "nch-b-ench" is a clumsy mouthful. Finch is already a well-known app and fintech name. Playful rather than professional. |
| 8 | rookbench.com | Short. Chess piece and bird. | "Rook" means to swindle, and "rookie" means novice. Both are poor signals for a studio selling expertise. |
| 9 | larchtools.com | Keeps the good "larch" root. | "Tools" implies a product vendor or utility, not a studio. |
| 10 | larchstack.com | Immediately reads as software. | "Stack" is overused. Sounds like a framework or product, and loses the craft feel of "bench". |
| 11 | tallbench.com | Easy to spell. | Means nothing. A "tall bench" is a bar stool; reads as a furniture shop. |

Notes on the other options:

- `larchbench.com` is the pick if the wood-and-craft story matters more than familiarity.
- `oxbench.com` is the pick if brevity and strength matter more than elegance.
- Avoid the `-tools` and `-stack` variants when positioning as a studio. They steer toward a product company.

## Availability and conflict checks (run 2026-10-27)

### Domain registration

Checked against the Verisign `.com` registry (RDAP). A "not found" response means the name is not registered. A known registered domain (`example.com`) was used as a control and returned a record, so the method works.

| Domain | Result |
|--------|--------|
| heronbench.com | Not registered |
| larchbench.com | Not registered |
| oxbench.com | Not registered |
| tealbench.com, kestrelbench.com, basaltbench.com, finchbench.com, rookbench.com, tallbench.com, larchstack.com, larchtools.com | Not registered |

Caveats:

- This does not show whether a name is held for resale at a premium price or about to expire. Confirm at a registrar before relying on it.
- `.com.au`, `.net`, `.dev` and `.studio` variants were not checked.

### Social handles for "heronbench"

Checked without signing in, so a suspended, reserved or recently deleted handle may not show up.

| Platform | Handle | Result |
|----------|--------|--------|
| GitHub | `github.com/heronbench` | Free (404) |
| npm | `~heronbench` | Free (scope not found) |
| X | `@heronbench` | Free ("account doesn't exist") |
| Instagram | `@heronbench` | Free ("profile isn't available") |
| LinkedIn | `/company/heronbench` | Free (page not found) |
| YouTube | `@heronbench` | Free (404) |
| Bluesky | `heronbench.bsky.social` | Free (profile not found) |
| Reddit | `u/heronbench` | Not checked (site blocked in the browser used) |

### Trademark: IP Australia (Australian Trade Mark Search)

| Search | Result |
|--------|--------|
| `heronbench` | 0 results |
| `heron bench` | 0 results |
| `heron*` | 176 results (first 100 reviewed) |

No identical or compound "Heron Bench" mark exists in Australia. The `heron*` hits are mostly unrelated owners and goods. The ones in software-adjacent classes (9, 35, 42) worth watching:

- **HERON** (class 9), owned by Rajant Corporation, registered. An exact word mark in a software-adjacent class. `HERONBENCH` is a different, longer mark, but this is the most likely thing to be raised by an examiner or owner.
- **HERON THERAPEUTICS / ZYNRELEF / APONVIE** (class 42, 44), owned by Heron Therapeutics, Inc. Pharmaceutical field; unlikely to conflict.
- **HERON PRESTON** (classes 9, 18, 25, 35), a fashion brand. Different field.
- **ROBOTUNITS** (classes 6, 7, 9, 42), owned by HERON Innovations Factory GmbH. Industrial robotics.

Conclusion: no blocking conflict found, with a low-to-moderate watch item on `HERON` in class 9.

### Other finding: "Heron-Bench" in the AI space

"Heron-Bench" is an existing Japanese vision-language model benchmark. Searching for the name surfaces it first. It is not a trademark, but it could make the name harder to search for among AI and developer audiences, and it reinforces the "benchmark" reading of "bench".

## Not checked / next steps

- [ ] Register `heronbench.com` (and consider `.com.au` and `.dev`).
- [ ] Claim the GitHub org, npm scope, X, Instagram, LinkedIn, YouTube and Bluesky handles listed above.
- [ ] Check Reddit manually.
- [ ] Review the remaining 76 `heron*` IP Australia results (page 2).
- [ ] Search the US register (USPTO) and other target markets. Not done.
- [ ] Consider a professional clearance search or a trade mark attorney before filing, particularly because of the `HERON` class 9 registration.
