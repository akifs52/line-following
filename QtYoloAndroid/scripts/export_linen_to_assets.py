from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from ultralytics import YOLO


def resolve_paths(model_arg: str, export_dir_arg: str, assets_dir_arg: str) -> tuple[Path, Path, Path]:
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent
    repo_dir = project_dir.parent

    model_path = Path(model_arg)
    if not model_path.is_absolute():
        model_path = (repo_dir / model_path).resolve()

    export_dir = Path(export_dir_arg)
    if not export_dir.is_absolute():
        export_dir = (project_dir / export_dir).resolve()

    assets_dir = Path(assets_dir_arg)
    if not assets_dir.is_absolute():
        assets_dir = (project_dir / assets_dir).resolve()

    return model_path, export_dir, assets_dir


def ensure_exists(path: Path, kind: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{kind} not found: {path}")


def copy_export_to_assets(export_dir: Path, assets_dir: Path) -> tuple[Path, Path]:
    param_src = export_dir / "model.ncnn.param"
    bin_src = export_dir / "model.ncnn.bin"
    ensure_exists(param_src, "NCNN param")
    ensure_exists(bin_src, "NCNN bin")

    assets_dir.mkdir(parents=True, exist_ok=True)
    param_dst = assets_dir / "yolo11.param"
    bin_dst = assets_dir / "yolo11.bin"
    shutil.copy2(param_src, param_dst)
    shutil.copy2(bin_src, bin_dst)
    return param_dst, bin_dst


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export linen.pt (YOLO11) to NCNN and copy to QtYoloAndroid/assets as yolo11.param/bin."
    )
    parser.add_argument("--model", default="linen.pt", help="Path to .pt model (default: linen.pt in repo root).")
    parser.add_argument(
        "--export-dir",
        default="models/linen_ncnn_model",
        help="Directory where NCNN export will be written (default: QtYoloAndroid/models/linen_ncnn_model).",
    )
    parser.add_argument(
        "--assets-dir",
        default="assets",
        help="Qt asset directory to receive yolo11.param/bin (default: QtYoloAndroid/assets).",
    )
    parser.add_argument("--imgsz", type=int, default=640, help="Export image size.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_path, export_dir, assets_dir = resolve_paths(args.model, args.export_dir, args.assets_dir)
    ensure_exists(model_path, "Model")

    export_dir.parent.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] Loading model: {model_path}")
    model = YOLO(str(model_path))
    print(f"      task={model.task}, classes={model.names}")

    print(f"[2/3] Exporting to NCNN: {export_dir}")
    exported = model.export(format="ncnn", imgsz=args.imgsz)
    exported_dir = Path(exported).resolve()
    if exported_dir != export_dir:
        if export_dir.exists():
            shutil.rmtree(export_dir)
        shutil.move(str(exported_dir), str(export_dir))
    print(f"      export output={export_dir}")

    print(f"[3/3] Copying assets to: {assets_dir}")
    param_dst, bin_dst = copy_export_to_assets(export_dir, assets_dir)
    print("Done.")
    print(f"      {param_dst}")
    print(f"      {bin_dst}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
