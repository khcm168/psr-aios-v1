from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


SLIDE_W = 12192000
SLIDE_H = 6858000
MARGIN_X = 560000
TITLE_Y = 350000
BODY_Y = 1100000
FOOTER_Y = 6380000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="n1_report_ppt",
        description="Create a compact editable PPTX from an N1 report-pack JSON file.",
    )
    parser.add_argument(
        "--json",
        default="data/report_packs/n1_report_pack_2026-04-27.json",
        help="Path to the n1_report_pack JSON file.",
    )
    parser.add_argument(
        "--output",
        default="data/report_packs/N1_report_2026-04-27.pptx",
        help="Path for the generated PPTX.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=6,
        help="Maximum rows shown per section slide.",
    )
    return parser.parse_args()


def main() -> None:
    from app.operation_log import try_append_operation_log

    args = parse_args()
    json_path = Path(args.json)
    output_path = Path(args.output)
    try:
        pack = json.loads(json_path.read_text(encoding="utf-8"))
        slides = build_slides(pack, max_rows=args.max_rows)
        write_pptx(output_path, slides)
        print(f"Wrote {output_path}")
        try_append_operation_log(
            operation="n1_report_ppt",
            result="success",
            purpose="Create editable PowerPoint draft from N1 report JSON pack.",
            variables={
                "json": str(json_path),
                "output": str(output_path),
                "max_rows": args.max_rows,
                "slide_count": len(slides),
            },
            details=f"Wrote {output_path}",
        )
    except Exception as exc:
        try_append_operation_log(
            operation="n1_report_ppt",
            result="failure",
            purpose="Create editable PowerPoint draft from N1 report JSON pack.",
            variables={
                "json": str(json_path),
                "output": str(output_path),
                "max_rows": args.max_rows,
            },
            details=str(exc),
        )
        raise


def build_slides(pack: dict[str, Any], max_rows: int) -> list[dict[str, Any]]:
    report_titles = [report["title"] for report in pack.get("reports", [])]
    source_title = pack.get("source", {}).get("actual_workbook_title") or pack.get("source", {}).get(
        "expected_workbook_title", ""
    )
    slides: list[dict[str, Any]] = [
        {
            "kind": "cover",
            "title": "N1 週報 / 地區業績營運報告",
            "subtitle": _date_from_titles(report_titles) or "2026-04-27",
            "kicker": source_title,
            "lines": report_titles,
        }
    ]

    for section in pack.get("sections", []):
        slides.append(
            {
                "kind": "section",
                "title": section.get("tab", "Section"),
                "status": section.get("status", ""),
                "headers": section.get("headers", []),
                "rows": section.get("rows", [])[:max_rows],
                "source_row_count": section.get("source_row_count", 0),
            }
        )

    slides.append(
        {
            "kind": "close",
            "title": "Follow-up Focus",
            "lines": _follow_up_lines(pack),
        }
    )
    return slides


def write_pptx(output_path: Path, slides: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", ZIP_DEFLATED) as pptx:
        _write_static_parts(pptx, len(slides))
        for index, slide in enumerate(slides, start=1):
            pptx.writestr(f"ppt/slides/slide{index}.xml", _slide_xml(index, slide))
            pptx.writestr(f"ppt/slides/_rels/slide{index}.xml.rels", _slide_rels_xml())


def _slide_xml(index: int, slide: dict[str, Any]) -> str:
    shapes = [_background()]
    if slide["kind"] == "cover":
        shapes.extend(_cover_shapes(slide))
    elif slide["kind"] == "close":
        shapes.extend(_close_shapes(slide))
    else:
        shapes.extend(_section_shapes(slide))
    shapes.append(
        _text_box(
            10500000,
            FOOTER_Y,
            1100000,
            260000,
            f"{index}",
            size=1100,
            color="667085",
            align="r",
        )
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
      {''.join(shapes)}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>"""


def _cover_shapes(slide: dict[str, Any]) -> list[str]:
    shapes = [
        _rect(0, 0, 220000, SLIDE_H, "2F855A", line="2F855A"),
        _text_box(MARGIN_X, 580000, 9000000, 450000, "N1 Report Pack", size=1800, color="2F855A"),
        _text_box(MARGIN_X, 1450000, 9400000, 1450000, slide["title"], size=3900, bold=True),
        _text_box(MARGIN_X, 3100000, 6000000, 520000, slide["subtitle"], size=2400, color="475467"),
        _text_box(MARGIN_X, 4100000, 9800000, 450000, slide.get("kicker", ""), size=1600, color="667085"),
    ]
    for offset, line in enumerate(slide.get("lines", [])[:2]):
        shapes.append(_text_box(MARGIN_X, 4850000 + offset * 380000, 9000000, 280000, line, size=1450))
    return shapes


def _section_shapes(slide: dict[str, Any]) -> list[str]:
    shapes = [
        _text_box(MARGIN_X, TITLE_Y, 9000000, 470000, slide["title"], size=2700, bold=True),
        _rect(MARGIN_X, 910000, 10800000, 20000, "2F855A", line="2F855A"),
    ]
    if slide.get("status") != "ok":
        shapes.append(
            _text_box(MARGIN_X, BODY_Y, 10000000, 420000, "No rows included in this section.", size=1800)
        )
        return shapes

    headers = [str(header) for header in slide.get("headers", [])[:4]]
    rows = slide.get("rows", [])
    if not rows:
        shapes.append(_text_box(MARGIN_X, BODY_Y, 10000000, 420000, "No rows found.", size=1800))
        return shapes

    y = BODY_Y
    row_h = 720000
    col_w = 2600000
    for col, header in enumerate(headers):
        shapes.append(
            _text_box(
                MARGIN_X + col * col_w,
                y,
                col_w - 120000,
                280000,
                header,
                size=1150,
                bold=True,
                color="2F855A",
            )
        )
    y += 360000
    shapes.append(_rect(MARGIN_X, y - 70000, 10500000, 12000, "D0D5DD", line="D0D5DD"))

    for row in rows[:6]:
        for col, header in enumerate(headers):
            text = _compact_text(row.get(header, ""), 120)
            shapes.append(
                _text_box(
                    MARGIN_X + col * col_w,
                    y,
                    col_w - 120000,
                    row_h,
                    text,
                    size=930,
                    color="344054",
                )
            )
        y += row_h + 90000

    shown = min(len(rows), 6)
    total = slide.get("source_row_count") or len(rows)
    shapes.append(
        _text_box(
            MARGIN_X,
            FOOTER_Y,
            7800000,
            260000,
            f"Showing {shown} of {total} source rows",
            size=1050,
            color="667085",
        )
    )
    return shapes


def _close_shapes(slide: dict[str, Any]) -> list[str]:
    shapes = [
        _text_box(MARGIN_X, 620000, 9600000, 850000, slide["title"], size=3400, bold=True),
        _rect(MARGIN_X, 1600000, 10800000, 20000, "2F855A", line="2F855A"),
    ]
    y = 2200000
    for line in slide.get("lines", [])[:7]:
        shapes.append(_text_box(MARGIN_X, y, 10000000, 420000, f"• {line}", size=1650))
        y += 560000
    return shapes


def _text_box(
    x: int,
    y: int,
    w: int,
    h: int,
    text: str,
    *,
    size: int = 1400,
    color: str = "101828",
    bold: bool = False,
    align: str = "l",
) -> str:
    runs = []
    for line_index, line in enumerate(str(text).splitlines() or [""]):
        br = "<a:br/>" if line_index else ""
        runs.append(
            f"""{br}<a:r><a:rPr lang="zh-TW" sz="{size}"{' b="1"' if bold else ''}><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:latin typeface="Microsoft JhengHei"/><a:ea typeface="Microsoft JhengHei"/></a:rPr><a:t>{escape(line)}</a:t></a:r>"""
        )
    return f"""
      <p:sp>
        <p:nvSpPr><p:cNvPr id="{_next_id()}" name="Text"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr>
        <p:txBody><a:bodyPr wrap="square" rtlCol="0"/><a:lstStyle/><a:p><a:pPr algn="{align}"/>{''.join(runs)}<a:endParaRPr lang="zh-TW" sz="{size}"/></a:p></p:txBody>
      </p:sp>"""


def _rect(x: int, y: int, w: int, h: int, fill: str, *, line: str = "FFFFFF") -> str:
    return f"""
      <p:sp>
        <p:nvSpPr><p:cNvPr id="{_next_id()}" name="Shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{fill}"/></a:solidFill><a:ln><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln></p:spPr>
      </p:sp>"""


def _background() -> str:
    return _rect(0, 0, SLIDE_W, SLIDE_H, "F9FAFB", line="F9FAFB")


_ID = 1


def _next_id() -> int:
    global _ID
    _ID += 1
    return _ID


def _compact_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _date_from_titles(titles: list[str]) -> str:
    for title in titles:
        parts = title.split()
        for part in parts:
            if len(part) == 10 and part[4] == "-" and part[7] == "-":
                return part
    return ""


def _follow_up_lines(pack: dict[str, Any]) -> list[str]:
    lines = []
    for section in pack.get("sections", []):
        if section.get("status") == "ok":
            rows = section.get("rows", [])
            lines.append(f"{section.get('tab')}: {len(rows)} items captured")
    return lines or ["Review JSON pack for captured source rows.", "Confirm priority actions before final delivery."]


def _slide_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>"""


def _write_static_parts(pptx: ZipFile, slide_count: int) -> None:
    pptx.writestr("[Content_Types].xml", _content_types_xml(slide_count))
    pptx.writestr("_rels/.rels", _root_rels_xml())
    pptx.writestr("docProps/app.xml", _app_xml(slide_count))
    pptx.writestr("docProps/core.xml", _core_xml())
    pptx.writestr("ppt/presentation.xml", _presentation_xml(slide_count))
    pptx.writestr("ppt/_rels/presentation.xml.rels", _presentation_rels_xml(slide_count))
    pptx.writestr("ppt/slideMasters/slideMaster1.xml", _slide_master_xml())
    pptx.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", _slide_master_rels_xml())
    pptx.writestr("ppt/slideLayouts/slideLayout1.xml", _slide_layout_xml())
    pptx.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", _slide_layout_rels_xml())
    pptx.writestr("ppt/theme/theme1.xml", _theme_xml())


def _content_types_xml(slide_count: int) -> str:
    slides = "\n".join(
        f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for i in range(1, slide_count + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  {slides}
</Types>"""


def _root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""


def _presentation_xml(slide_count: int) -> str:
    slide_ids = "\n".join(
        f'<p:sldId id="{255 + i}" r:id="rId{i}"/>' for i in range(1, slide_count + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId{slide_count + 1}"/></p:sldMasterIdLst>
  <p:sldIdLst>{slide_ids}</p:sldIdLst>
  <p:sldSz cx="{SLIDE_W}" cy="{SLIDE_H}" type="wide"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>"""


def _presentation_rels_xml(slide_count: int) -> str:
    rels = [
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
        for i in range(1, slide_count + 1)
    ]
    rels.append(
        f'<Relationship Id="rId{slide_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{''.join(rels)}</Relationships>"""


def _slide_master_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles>
</p:sldMaster>"""


def _slide_master_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>"""


def _slide_layout_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>"""


def _slide_layout_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>"""


def _theme_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="N1">
  <a:themeElements>
    <a:clrScheme name="N1"><a:dk1><a:srgbClr val="101828"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="344054"/></a:dk2><a:lt2><a:srgbClr val="F9FAFB"/></a:lt2><a:accent1><a:srgbClr val="2F855A"/></a:accent1><a:accent2><a:srgbClr val="0E7490"/></a:accent2><a:accent3><a:srgbClr val="F79009"/></a:accent3><a:accent4><a:srgbClr val="475467"/></a:accent4><a:accent5><a:srgbClr val="667085"/></a:accent5><a:accent6><a:srgbClr val="D0D5DD"/></a:accent6><a:hlink><a:srgbClr val="0E7490"/></a:hlink><a:folHlink><a:srgbClr val="475467"/></a:folHlink></a:clrScheme>
    <a:fontScheme name="N1"><a:majorFont><a:latin typeface="Microsoft JhengHei"/><a:ea typeface="Microsoft JhengHei"/></a:majorFont><a:minorFont><a:latin typeface="Microsoft JhengHei"/><a:ea typeface="Microsoft JhengHei"/></a:minorFont></a:fontScheme>
    <a:fmtScheme name="N1"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme>
  </a:themeElements>
</a:theme>"""


def _app_xml(slide_count: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>n1_report_ppt</Application><PresentationFormat>On-screen Show (16:9)</PresentationFormat><Slides>{slide_count}</Slides></Properties>"""


def _core_xml() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>N1 Report</dc:title><dc:creator>n1_report_ppt</dc:creator><cp:lastModifiedBy>n1_report_ppt</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>"""


if __name__ == "__main__":
    main()
