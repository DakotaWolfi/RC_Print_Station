"""Package exact editable HMI bytes, without changing either project."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
ORIGINAL_SHA="a8c8f53e1fa99f675c8aa562a95ea5dcb5d9ff88483d3ed6f9c9dde0084d0308"


def archive(path):
    output=path.with_suffix(".zip")
    info=zipfile.ZipInfo(path.name,date_time=(2026,11,25,0,0,0))
    info.compress_type=zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        z.writestr(info,path.read_bytes(),compresslevel=9)
    with zipfile.ZipFile(output) as z:
        assert z.read(path.name)==path.read_bytes()
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tft",type=Path,required=True,help="Matching locally compiled TFT")
    args=parser.parse_args()
    original=ROOT/"hmi/reference/FMI_RC_Printstation_working.HMI"
    if not original.exists():
        with zipfile.ZipFile(original.with_suffix(".zip")) as z:
            original.write_bytes(z.read(original.name))
    if hashlib.sha256(original.read_bytes()).hexdigest()!=ORIGINAL_SHA:
        raise SystemExit("Reference HMI differs from the original; refusing to replace its archive")
    candidate=ROOT/"hmi/build/FMI_RC_native_v0_3.HMI"
    paths=[original,candidate,args.tft]
    archives=[archive(original),archive(candidate)]
    manifest={"candidate":"v0.3","target":"NX8048T070_011R","rotation":270,
        "resolution":[480,800],"baud":115200,"encoding":"iso-8859-15","protocol":3,
        "nxwright_commit":"e9443a409cc9deb866db7486854fa962d382accc",
        "vendor_firmware_editor":"1.68.2",
        "files":[{"name":p.name,"size_bytes":p.stat().st_size,
                  "sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths+archives]}
    (ROOT/"hmi/build/manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("Verified both ZIPs against the original HMI bytes; wrote manifest.json")


if __name__=="__main__":
    main()
