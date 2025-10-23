# app/charts/blocks.py
"""
Workout program presets for dropdown prefill in the Workout tab.
Pure data module (no Flask/DB).
"""

from copy import deepcopy

# ───────────────────────── GK preset used for TO* & B* ─────────────────────────
GK_PRESET = [
    {"Workout": "1/2 KICK BACK",   "Rings": "", "Notes": ""},
    {"Workout": "KICK BACK",       "Rings": "", "Notes": ""},
    {"Workout": "SIDE DIAG KICKS", "Rings": "", "Notes": ""},
]

# ---- C1–C5 ----
C1_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "PUSH LEGS", "Rings": "S", "Notes": ""},
        {"Workout": "FROG", "Rings": "S", "Notes": ""},
        {"Workout": "KICKS SIDE", "Rings": "I", "Notes": ""},
        {"Workout": "KICK SIDE TURN", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE TRIANGLES", "Rings": "S+S", "Notes": ""},
        {"Workout": "SIDE CIRCLES", "Rings": "S+S", "Notes": ""},
        {"Workout": "1 LEG FROG", "Rings": "IOP", "Notes": ""},
        {"Workout": "BENDING LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS BACK", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS ON KNEE", "Rings": "S", "Notes": ""},
        {"Workout": "ARMS BACK/UP", "Rings": "S", "Notes": ""},
        {"Workout": "BICEPS SEATED", "Rings": "I", "Notes": ""},
        {"Workout": "ROW SEATED", "Rings": "I", "Notes": ""},
        {"Workout": "TRICEPS OPP", "Rings": "Sop", "Notes": ""},
    ],
    "GK": []
}
C2_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP 90", "Rings": "-", "Notes": ""},
        {"Workout": "ELBOW KNEES", "Rings": "S", "Notes": ""},
        {"Workout": "BICYCLE", "Rings": "S", "Notes": ""},
        {"Workout": "LEGS EXTENSION", "Rings": "S", "Notes": ""},
        {"Workout": "CROSSED KICKS", "Rings": "Sop", "Notes": ""},
        {"Workout": "1 LEG FROG UP/DOWN", "Rings": "Iop", "Notes": ""},
        {"Workout": "SIDE BICYCLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE KICK CHEST", "Rings": "I", "Notes": ""},
        {"Workout": "HIPS UP", "Rings": "-", "Notes": ""},
        {"Workout": "1/2 KICKS BACK", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS ON KNEE STR.", "Rings": "I", "Notes": ""},
        {"Workout": "1/2 KICKS ON KNEE", "Rings": "I", "Notes": ""},
        {"Workout": "SHOULDER UP", "Rings": "-", "Notes": ""},
        {"Workout": "ARMS LIFT L.D.", "Rings": "S", "Notes": ""},
        {"Workout": "BACK BUTTERFLY SEAT", "Rings": "I", "Notes": ""},
        {"Workout": "PUSH ARMS UP", "Rings": "S", "Notes": ""},
    ], "GK": []
}
C3_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP ALT", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TWIST STRAIGHT", "Rings": "S", "Notes": ""},
        {"Workout": "DOUBLE KICKS TURN", "Rings": "S", "Notes": ""},
        {"Workout": "FROGGY", "Rings": "S", "Notes": ""},
        {"Workout": "DIAGONAL KICKS", "Rings": "I", "Notes": ""},
        {"Workout": "LEGS EXTENSION ALT", "Rings": "I", "Notes": ""},
        {"Workout": "1/2 KICK SIDE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE BEND & EXTEND", "Rings": "I", "Notes": ""},
        {"Workout": "SWAY", "Rings": "-", "Notes": ""},
        {"Workout": "PELVIS UP", "Rings": "-", "Notes": ""},
        {"Workout": "CIRCLES ON KNEE", "Rings": "I", "Notes": ""},
        {"Workout": "1/2 TRIANGLES O.K.", "Rings": "I", "Notes": ""},
        {"Workout": "BOXING", "Rings": "S", "Notes": ""},
        {"Workout": "SIDE ARM TURN", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED ROW", "Rings": "Iop", "Notes": ""},
        {"Workout": "TRIC OPP SEATED", "Rings": "Iop", "Notes": ""},
    ], "GK": []
}
C4_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE KICKS", "Rings": "-", "Notes": ""},
        {"Workout": "FETAL CHEST UP", "Rings": "-", "Notes": ""},
        {"Workout": "DOUBLE PUSH LEGS", "Rings": "S", "Notes": ""},
        {"Workout": "REVERSE BICYCLE", "Rings": "S", "Notes": ""},
        {"Workout": "SIDE KICKS PUMP", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS SIDE TURN REV", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "1 LEG FROG OP/CL", "Rings": "Iop", "Notes": ""},
        {"Workout": "CAT UP", "Rings": "-", "Notes": ""},
        {"Workout": "BENDING LEGS ALT", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS ON KNEE", "Rings": "s+s", "Notes": ""},
        {"Workout": "BEND/EXTEND ON KNEE", "Rings": "I", "Notes": ""},
        {"Workout": "SHOULDER ELBOW B.D.", "Rings": "S", "Notes": ""},
        {"Workout": "SIDE CIRCLES", "Rings": "S", "Notes": ""},
        {"Workout": "ARMS LIFT", "Rings": "S", "Notes": ""},
        {"Workout": "BICEPS TWIST", "Rings": "Iop", "Notes": ""},
    ], "GK": []
}
C5_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "DOUBLE KICKS TURN REV", "Rings": "S", "Notes": ""},
        {"Workout": "ALT FROG", "Rings": "S", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "TRIANGLES ON STOM", "Rings": "I", "Notes": ""},
        {"Workout": "1/2 CIRCLES ON KNEE", "Rings": "I", "Notes": ""},
        {"Workout": "TRIANGLES ON KNEE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS OPP", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
    ], "GK": []
}

# ---- V1–V5 ----
V1_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "PUSH LEGS", "Rings": "S", "Notes": ""},
        {"Workout": "FROG", "Rings": "S", "Notes": ""},
        {"Workout": "BICYCLE", "Rings": "S", "Notes": ""},
        {"Workout": "HIPS UP", "Rings": "-", "Notes": ""},
        {"Workout": "KICKS UP", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS SIDE", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS SIDE TURN", "Rings": "I", "Notes": ""},
        {"Workout": "BENDING LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS BACK", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS ON KNEE", "Rings": "S", "Notes": ""},
        {"Workout": "ARMS BACK/UP", "Rings": "S", "Notes": ""},
        {"Workout": "BICEPS SEATED", "Rings": "I", "Notes": ""},
        {"Workout": "ROW SEATED", "Rings": "I", "Notes": ""},
        {"Workout": "TRICEPS OPP", "Rings": "Sop", "Notes": ""},
    ], "GK": []
}
V2_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP 90", "Rings": "-", "Notes": ""},
        {"Workout": "ELBOW KNEES", "Rings": "S", "Notes": ""},
        {"Workout": "SCISSORS", "Rings": "S", "Notes": ""},
        {"Workout": "EAGLE", "Rings": "S", "Notes": ""},
        {"Workout": "SWAY", "Rings": "-", "Notes": ""},
        {"Workout": "STOMACH UP/DOWN", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TO CHEST", "Rings": "I", "Notes": ""},
        {"Workout": "LEGS EXTENSION", "Rings": "S", "Notes": ""},
        {"Workout": "SIDE TRIANGLES", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS ON KNEE STR", "Rings": "I", "Notes": ""},
        {"Workout": "1/2 KICKS ON KNEE", "Rings": "I", "Notes": ""},
        {"Workout": "SHOULDER UP", "Rings": "-", "Notes": ""},
        {"Workout": "ARMS LIFT L.D.", "Rings": "S", "Notes": ""},
        {"Workout": "BACK BUTTERFLY SEAT", "Rings": "I", "Notes": ""},
        {"Workout": "PUSH ARMS UP", "Rings": "S", "Notes": ""},
    ], "GK": []
}
V3_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP ALT", "Rings": "-", "Notes": ""},
        {"Workout": "REVERSE CRUNCH", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TWIST STRAIGHT", "Rings": "S", "Notes": ""},
        {"Workout": "ELBOW KNEE STS", "Rings": "I", "Notes": ""},
        {"Workout": "KICK UP TOUCH", "Rings": "I", "Notes": ""},
        {"Workout": "LATERAL KICKS (inner)", "Rings": "I", "Notes": ""},
        {"Workout": "STOMACH TRIANGLES", "Rings": "-", "Notes": ""},
        {"Workout": "1/2 KICK SIDE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE BEND & EXTEND", "Rings": "I", "Notes": ""},
        {"Workout": "CHEST LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "BOXING", "Rings": "S", "Notes": ""},
        {"Workout": "SIDE ARM TURN", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED ROW", "Rings": "Iop", "Notes": ""},
        {"Workout": "TRIC OPP SEATED", "Rings": "Iop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ], "GK": []
}
V4_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE KICKS", "Rings": "-", "Notes": ""},
        {"Workout": "FETAL CHEST UP", "Rings": "-", "Notes": ""},
        {"Workout": "ELBOW KNEES", "Rings": "S", "Notes": ""},
        {"Workout": "REVERSE EAGLE", "Rings": "S", "Notes": ""},
        {"Workout": "SCISSORS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST U", "Rings": "I", "Notes": ""},
        {"Workout": "CAT UP", "Rings": "-", "Notes": ""},
        {"Workout": "CLIMBER", "Rings": "-", "Notes": ""},
        {"Workout": "KICKS SIDE TURN REV", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE CIRCLES ALT", "Rings": "I", "Notes": ""},
        {"Workout": "KICK DIAGONAL COMPL", "Rings": "I", "Notes": ""},
        {"Workout": "SHOULDER ELBOW B.D.", "Rings": "S", "Notes": ""},
        {"Workout": "ARMS LIFT", "Rings": "S", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ], "GK": []
}
V5_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ], "GK": []
}

# ---- TO1–TO5 ----
TO1_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "SCISSORS", "Rings": "S", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "S", "Notes": ""},
        {"Workout": "EAGLE", "Rings": "S", "Notes": ""},
        {"Workout": "HIPS UP", "Rings": "-", "Notes": ""},
        {"Workout": "KICKS UP", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS SIDE", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS SIDE TURN", "Rings": "I", "Notes": ""},
        {"Workout": "SUPERWOMAN", "Rings": "ALL", "Notes": ""},
        {"Workout": "BODY TWIST", "Rings": "Sop", "Notes": ""},
        {"Workout": "ARMS BACK/UP", "Rings": "S", "Notes": ""},
        {"Workout": "BICEPS SEATED", "Rings": "I", "Notes": ""},
        {"Workout": "ROW SEATED", "Rings": "I", "Notes": ""},
        {"Workout": "TRICEPS OPP", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ],
    "GK": deepcopy(GK_PRESET),
}
TO2_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP 90", "Rings": "-", "Notes": ""},
        {"Workout": "1 LEG TWIST", "Rings": "I", "Notes": ""},
        {"Workout": "HIPS SIDE TO SIDE", "Rings": "I", "Notes": ""},
        {"Workout": "ELBOW KNEE (feet down)", "Rings": "-", "Notes": ""},
        {"Workout": "SWAY", "Rings": "-", "Notes": ""},
        {"Workout": "STOMACH UP/DOWN", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TO CHEST", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS DIAGONAL", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE TRIANGLES", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "HIPS SIDE TO SIDE BD", "Rings": "I", "Notes": ""},
        {"Workout": "SHOULDER UP", "Rings": "-", "Notes": ""},
        {"Workout": "ARMS LIFT L.D.", "Rings": "S", "Notes": ""},
        {"Workout": "BACK BUTTERFLY SEAT", "Rings": "I", "Notes": ""},
        {"Workout": "PUSH ARMS UP", "Rings": "S", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ],
    "GK": deepcopy(GK_PRESET),
}
TO3_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP ALT", "Rings": "-", "Notes": ""},
        {"Workout": "REVERSE CRUNCH", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TWIST STRAIGHT", "Rings": "S", "Notes": ""},
        {"Workout": "KICK UP ALT", "Rings": "S", "Notes": ""},
        {"Workout": "ELBOW KNEE STS", "Rings": "I", "Notes": ""},
        {"Workout": "KICK UP TOUCH", "Rings": "I", "Notes": ""},
        {"Workout": "LATERAL KICKS (inner)", "Rings": "I", "Notes": ""},
        {"Workout": "STOMACH TRIANGLES", "Rings": "-", "Notes": ""},
        {"Workout": "1/2 KICK SIDE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE BEND & EXTEND", "Rings": "I", "Notes": ""},
        {"Workout": "CHEST LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "BOXING", "Rings": "S", "Notes": ""},
        {"Workout": "SIDE ARM TURN", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED ROW", "Rings": "Iop", "Notes": ""},
        {"Workout": "TRIC OPP SEATED", "Rings": "Iop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ],
    "GK": deepcopy(GK_PRESET),
}
TO4_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE KICKS", "Rings": "-", "Notes": ""},
        {"Workout": "FETAL CHEST UP", "Rings": "-", "Notes": ""},
        {"Workout": "ELBOW KNEES", "Rings": "S", "Notes": ""},
        {"Workout": "REVERSE EAGLE", "Rings": "S", "Notes": ""},
        {"Workout": "SCISSORS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST U", "Rings": "I", "Notes": ""},
        {"Workout": "CAT UP", "Rings": "-", "Notes": ""},
        {"Workout": "CLIMBER", "Rings": "-", "Notes": ""},
        {"Workout": "KICKS SIDE TURN REV", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE CIRCLES ALT", "Rings": "I", "Notes": ""},
        {"Workout": "KICK DIAGONAL COMPL", "Rings": "I", "Notes": ""},
        {"Workout": "SHOULDER ELBOW B.D.", "Rings": "S", "Notes": ""},
        {"Workout": "ARMS LIFT", "Rings": "S", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ],
    "GK": deepcopy(GK_PRESET),
}
TO5_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ],
    "GK": deepcopy(GK_PRESET),
}

# ---- B1–B15 ----
B1_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ],
    "GK": deepcopy(GK_PRESET),
}

# Build B2..B15 as deep copies of B1, each with its own dict (incl. GK)
B2_BLOCK  = deepcopy(B1_BLOCK)
B3_BLOCK  = deepcopy(B1_BLOCK)
B4_BLOCK  = deepcopy(B1_BLOCK)
B5_BLOCK  = deepcopy(B1_BLOCK)
B6_BLOCK  = deepcopy(B1_BLOCK)
B7_BLOCK  = deepcopy(B1_BLOCK)
B8_BLOCK  = deepcopy(B1_BLOCK)
B9_BLOCK  = deepcopy(B1_BLOCK)
B10_BLOCK = deepcopy(B1_BLOCK)
B11_BLOCK = deepcopy(B1_BLOCK)
B12_BLOCK = deepcopy(B1_BLOCK)
B13_BLOCK = deepcopy(B1_BLOCK)
B14_BLOCK = deepcopy(B1_BLOCK)
B15_BLOCK = deepcopy(B1_BLOCK)

WORKOUT_FALLBACKS = {
    "C1": C1_BLOCK, "C2": C2_BLOCK, "C3": C3_BLOCK, "C4": C4_BLOCK, "C5": C5_BLOCK,
    "V1": V1_BLOCK, "V2": V2_BLOCK, "V3": V3_BLOCK, "V4": V4_BLOCK, "V5": V5_BLOCK,
    "TO1": TO1_BLOCK, "TO2": TO2_BLOCK, "TO3": TO3_BLOCK, "TO4": TO4_BLOCK, "TO5": TO5_BLOCK,
    "B1": B1_BLOCK, "B2": B2_BLOCK, "B3": B3_BLOCK, "B4": B4_BLOCK, "B5": B5_BLOCK,
    "B6": B6_BLOCK, "B7": B7_BLOCK, "B8": B8_BLOCK, "B9": B9_BLOCK, "B10": B10_BLOCK,
    "B11": B11_BLOCK, "B12": B12_BLOCK, "B13": B13_BLOCK, "B14": B14_BLOCK, "B15": B15_BLOCK,
}

def get_blocks():
    return WORKOUT_FALLBACKS
