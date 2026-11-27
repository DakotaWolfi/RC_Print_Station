"""Normalised Linux touch calibration shared by the CLI and mapping tests."""
import re

ROTATIONS = (0, 90, 180, 270)
TARGETS = ((.12,.12),(.88,.12),(.88,.88),(.12,.88),(.50,.50))


def apply(matrix, point):
    a,b,c,d,e,f = matrix
    x,y = point
    return (a*x+b*y+c, d*x+e*y+f)


def rotation(degrees=0, *, swap=False, invert_x=False, invert_y=False):
    matrix = {
        0:(1,0,0,0,1,0), 90:(0,-1,1,1,0,0), 180:(-1,0,1,0,-1,1), 270:(0,1,0,-1,0,1)
    }[degrees]
    a,b,c,d,e,f = matrix
    if swap:
        a,b,d,e = b,a,e,d
    if invert_x:
        a,b,c = -a,-b,1-c
    if invert_y:
        d,e,f = -d,-e,1-f
    return a,b,c,d,e,f


def solve(matrix, rhs):
    rows = [list(row)+[value] for row,value in zip(matrix,rhs)]
    for i in range(3):
        pivot = max(range(i,3),key=lambda n:abs(rows[n][i]))
        rows[i],rows[pivot] = rows[pivot],rows[i]
        divisor = rows[i][i]
        if abs(divisor)<1e-7:
            raise ValueError("Calibration points must span both axes")
        rows[i] = [v/divisor for v in rows[i]]
        for j in range(3):
            if j!=i:
                factor = rows[j][i]
                rows[j] = [p-factor*q for p,q in zip(rows[j],rows[i])]
    return tuple(row[-1] for row in rows)


def fit(raw, targets=TARGETS, compositor_rotation=0):
    if len(raw)!=len(targets) or len(raw)<4 or any(not 0<=v<=1 for point in raw for v in point):
        raise ValueError("Invalid calibration sample")
    system = [(x,y,1) for x,y in raw]
    mapped = [apply(rotation(-compositor_rotation%360), target) for target in targets]
    columns = tuple(zip(*system))
    dot = lambda a,b: sum(x*y for x,y in zip(a,b))
    normal = [[dot(a,b) for b in columns] for a in columns]
    matrix=tuple(coefficient for axis in zip(*mapped) for coefficient in solve(normal,[dot(c,axis) for c in columns]))
    if (max(abs(a-b) for r,target in zip(raw,mapped) for a,b in zip(apply(matrix,r),target))>.055
            or any(abs(value)>3 for value in matrix)):
        raise ValueError("Calibration points inconsistent. Repeat with single, centered taps.")
    return matrix


def rule(matrix, *, device_path):
    if not device_path or not re.fullmatch(r"[A-Za-z0-9_./:+-]{1,180}",device_path):
        raise ValueError("Use the exact udev ID_PATH for this touchscreen")
    values = " ".join(f"{value:.6g}" for value in matrix)
    return ('SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_TOUCHSCREEN}=="1", '
            f'ENV{{ID_PATH}}=="{device_path}", ENV{{LIBINPUT_CALIBRATION_MATRIX}}:="{values}"\n')
