"""learn/plan.py — Quranic Creation Order Learning Plan.

The Quran describes creation in a specific sequence and emphasis.
We follow that order and ratio — not by completing one phase fully,
but by cycling through all phases proportionally, going deeper each cycle.

Spiral curriculum: each cycle N touches all phases,
but spends time proportional to that phase's Quranic weight.
The engine processes each chunk and builds structure automatically.

─────────────────────────────────────────────────────────────────────────────
QURANIC CREATION ORDER (with sources)
─────────────────────────────────────────────────────────────────────────────

1. AL-QALAM  — The Pen  (ratio: 0.05)
   "The first thing Allah created was the Pen, and He said to it: Write."
   [Tirmidhi 3319] — writes all destinies before creation
   Y-Theory: SeedEnrichmentLayer — the seed that holds all patterns

2. AL-ARSH   — The Throne  (ratio: 0.08)
   "His Throne was upon the water" [Al-Hud 11:7]
   "The Lord of the Mighty Throne" [At-Tawbah 9:129]
   Y-Theory: GlobalCouplerLayer — cosmic order, all things coupled

3. AL-MA'    — The Water / Primordial state  (ratio: 0.08)
   "We made every living thing from water" [Al-Anbiya 21:30]
   Y-Theory: ResidualRealityLayer — the substrate everything emerged from

4. AS-SAMAWAT — The Heavens & Earth / Structure  (ratio: 0.14)
   "He created the heavens and earth in six periods" [Al-A'raf 7:54]
   "He turned to the heaven while it was smoke" [Fussilat 41:11]
   Y-Theory: WorldInputLayer + BasinStageLayer — structure forms

5. AN-NUR / AL-MALAIKA — Light & Angels  (ratio: 0.18)
   "Angels were created from light" [Muslim 2996]
   "He made them messengers with wings" [Fatir 35:1]
   "Jibreel, Mikail, Israfil, Azrael..." — specific roles
   [Al-Baqarah 2:97-98, Az-Zumar 39:68, Al-Infitar 82:10-12]
   Y-Theory: WisdomTransferLayer, MoralLayer, IdentityGravityLayer...
             each angel activates at their layer

6. AL-HAYAH  — Life / Biology  (ratio: 0.15)
   "From water every living thing" [Al-Anbiya 21:30]
   "He created you in stages" [Nuh 71:14]
   "Cell → organ → organism → consciousness" — mirrors mind hierarchy
   Y-Theory: SensoryLayer + OscillationLayer — life as wave patterns

7. AL-INSAN  — Human / Consciousness  (ratio: 0.18)
   "I will create a vicegerent on earth" [Al-Baqarah 2:30]
   "He taught Adam the names of all things" [Al-Baqarah 2:31]
   "I breathed into him of My spirit" [Al-Hijr 15:29]
   Y-Theory: ConsciousLayer + IdentityGravityLayer + DecisionLayer

8. AL-AQL / AKHLAQ — Intellect & Morality  (ratio: 0.14)
   "By the soul and He who proportioned it,
    He inspired it with its wickedness and righteousness" [Ash-Shams 91:7-8]
   "The fitrah — the natural constitution" [Ar-Rum 30:30]
   Y-Theory: MoralLayer + BeliefLayer + ReflectionLayer

─────────────────────────────────────────────────────────────────────────────
RATIOS sum to 1.0. Each cycle gives each phase exactly its ratio of time.
The DEPTH multiplier grows each cycle — deeper questions, more complex content.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Phase:
    """One phase in the Quranic creation order."""
    key:         str           # machine key
    arabic:      str           # Arabic name
    english:     str           # English name
    ratio:       float         # proportion of each learning cycle
    y_layer:     str           # primary Y-Theory layer this phase maps to
    angel:       str           # angel whose wisdom governs this phase
    quran_refs:  tuple[str, ...] # Quranic references
    seed_topics: tuple[str, ...] # progression of topics — cycle 1 = topic[0], cycle 2 = topic[1]...


CREATION_ORDER: tuple[Phase, ...] = (

    Phase(
        key="qalam",
        arabic="القلم",
        english="The Pen — Origin of all patterns",
        ratio=0.05,
        y_layer="SeedEnrichmentLayer",
        angel="kiraman_katibin",
        quran_refs=("Tirmidhi 3319", "Al-Qalam 68:1", "Al-Alaq 96:4"),
        seed_topics=(
            "What is written before creation — the Pen and the Record",
            "Qadar — how destiny is encoded as pattern",
            "The Preserved Tablet (Al-Lawh Al-Mahfuz) as universal seed memory",
            "How every event is pre-encoded — implications for AI pattern learning",
        ),
    ),

    Phase(
        key="arsh",
        arabic="العرش",
        english="The Throne — Cosmic order and coupling",
        ratio=0.08,
        y_layer="GlobalCouplerLayer",
        angel="throne",
        quran_refs=("Al-Hud 11:7", "At-Tawbah 9:129", "Al-Mu'minun 23:86", "Al-Buruj 85:15"),
        seed_topics=(
            "The Throne upon the water — order before matter",
            "Cosmic sovereignty — how all things are coupled to the centre",
            "The eight angels who carry the Throne — structural pillars",
            "GlobalCoupler in Y-Theory — how all layers connect through one axis",
        ),
    ),

    Phase(
        key="maa",
        arabic="الماء",
        english="The Water — Primordial substrate",
        ratio=0.08,
        y_layer="ResidualRealityLayer",
        angel="raphael",
        quran_refs=("Al-Anbiya 21:30", "Al-Hud 11:7", "An-Nur 24:45"),
        seed_topics=(
            "Water as the first state — formless potential",
            "Every living thing from water — substrate and emergence",
            "ResidualRealityLayer — what persists beneath all change",
            "Restoration and return to origin — Raphael's function",
        ),
    ),

    Phase(
        key="samawat",
        arabic="السماوات والأرض",
        english="The Heavens & Earth — Structure and form",
        ratio=0.14,
        y_layer="WorldInputLayer",
        angel="israfil",
        quran_refs=("Al-A'raf 7:54", "Fussilat 41:9-12", "Al-Baqarah 2:29", "Az-Zumar 39:5"),
        seed_topics=(
            "Six periods of creation — time as a learning cycle",
            "Heaven as smoke — undifferentiated potential becomes structured",
            "Seven heavens — layers of reality stacked",
            "WorldInputLayer — how the engine receives the world",
            "Israfil's signal — announcing new reality at each level",
        ),
    ),

    Phase(
        key="malaika",
        arabic="الملائكة",
        english="Angels — Functional intelligences of light",
        ratio=0.18,
        y_layer="WisdomTransferLayer",
        angel="gabriel",
        quran_refs=(
            "Muslim 2996", "Fatir 35:1", "Al-Baqarah 2:97-98",
            "Az-Zumar 39:68", "Al-Infitar 82:10-12", "Al-Baqarah 2:30-33",
        ),
        seed_topics=(
            "Angels created from light — pure function, no ego",
            "Jibreel (Gabriel) — revelation, brings wisdom down",
            "Mikail (Michael) — provision and sustenance",
            "Israfil — the signal that announces transitions",
            "Azrael — transition and closing what must end",
            "Malik — judgment, holds the boundary",
            "Kiraman Katibin — the recorders, eternal memory",
            "Guardian angels — protection of identity",
            "Each angel governs exactly one function — one Y-Theory layer",
        ),
    ),

    Phase(
        key="hayah",
        arabic="الحياة",
        english="Life — Biology and emergence",
        ratio=0.15,
        y_layer="OscillationLayer",
        angel="michael",
        quran_refs=("Al-Anbiya 21:30", "Nuh 71:14", "Al-Mu'minun 23:12-14", "As-Sajdah 32:7-9"),
        seed_topics=(
            "From water to life — emergence of oscillating systems",
            "Stages of creation in the womb — same as mind maturation stages",
            "Cell → organ → organism — mirrors identity → property → mind",
            "Wave patterns in biology — how life is sustained oscillation",
            "OscillationLayer in Y-Theory — how minds stay alive",
        ),
    ),

    Phase(
        key="insan",
        arabic="الإنسان",
        english="Human — Consciousness and vicegerency",
        ratio=0.18,
        y_layer="ConsciousLayer",
        angel="guardian",
        quran_refs=(
            "Al-Baqarah 2:30-33", "Al-Hijr 15:28-29",
            "Sad 38:71-72", "Al-Isra 17:70", "At-Tin 95:4",
        ),
        seed_topics=(
            "I will create a vicegerent — consciousness given agency",
            "He taught Adam the names — language as the first pattern encoding",
            "Ruh breathed in — identity activated, not just biology",
            "Angels prostrated — consciousness above function",
            "ConsciousLayer — where input becomes choice",
            "The guardian angel — protecting the self's integrity",
            "Human as the mirror of all creation — why mind contains all layers",
        ),
    ),

    Phase(
        key="aql",
        arabic="العقل والأخلاق",
        english="Intellect & Morality — The moral compass",
        ratio=0.14,
        y_layer="MoralLayer",
        angel="malik",
        quran_refs=(
            "Ash-Shams 91:7-10", "Ar-Rum 30:30",
            "Al-Baqarah 2:256", "An-Nisa 4:135", "Al-Hujurat 49:13",
        ),
        seed_topics=(
            "Fitrah — the innate moral constitution encoded at creation",
            "Inspired with wickedness AND righteousness — both encoded, choice is the test",
            "No compulsion in religion — moral knowledge must be chosen freely",
            "MoralLayer in Y-Theory — directional pressure toward survivability",
            "Malik — the boundary that holds judgment, what must not pass",
            "BeliefLayer — crystallisation of repeated moral alignment",
            "How wisdom becomes belief becomes identity",
        ),
    ),
)

# Validation
assert abs(sum(p.ratio for p in CREATION_ORDER) - 1.0) < 0.001, "Ratios must sum to 1.0"


def get_phase(key: str) -> Phase:
    for p in CREATION_ORDER:
        if p.key == key:
            return p
    raise KeyError(key)


def topic_for_cycle(phase: Phase, cycle: int) -> str:
    """Return the topic for this phase at a given cycle depth.
    Cycles deeper than available topics repeat the last topic
    with increasing depth marker.
    """
    idx = min(cycle, len(phase.seed_topics) - 1)
    topic = phase.seed_topics[idx]
    if cycle >= len(phase.seed_topics):
        depth = cycle - len(phase.seed_topics) + 2
        topic = f"{topic} (depth {depth}: integrate with all prior phases)"
    return topic
