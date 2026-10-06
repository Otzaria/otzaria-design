"""אורז את הפלט ל-zip של Release: קבצים שטוחים, ממוינים, בתאריך קבוע — אותו פלט נותן אותו SHA-256."""
import argparse
import hashlib
import os
import re
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))


def art_version(out_dir):
    with open(os.path.join(out_dir, "assistant_art.isi"), encoding="utf-8") as f:
        return re.search(r'#define AA_ART_VERSION "([^"]+)"', f.read()).group(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(HERE, "out"), help="תיקיית הפלט של build_assistant_art.py")
    parser.add_argument("--dest", default=HERE, help="היכן לכתוב את ה-zip")
    args = parser.parse_args()

    version = art_version(args.out)
    path = os.path.join(args.dest, f"download-assistant-art-{version}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(os.listdir(args.out)):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(os.path.join(args.out, name), "rb") as f:
                archive.writestr(info, f.read())
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    print(f"{path}\nversion {version}\nsize {os.path.getsize(path)}\nsha256 {digest}")


if __name__ == "__main__":
    main()
