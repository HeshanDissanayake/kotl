#!/usr/bin/env python3
"""Build kotl-status-<version>.vsix from this folder with the standard library only (no npm/vsce).
Usage: python3 vscode-kotl/build_vsix.py OUT_DIR [BUILD]
BUILD (from deploy/kotl/install.sh) goes into the extension as BUILD, so it can tell when Kotl is
updated after it was installed."""
import json
import os
import sys
import zipfile
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["package.json", "extension.js", "format.js", "media/kotl.svg"]


def build(out_dir, build_id=""):
    pkg = json.load(open(os.path.join(HERE, "package.json")))
    manifest = f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="{pkg['name']}" Version="{pkg['version']}" Publisher="{pkg['publisher']}" />
    <DisplayName>{escape(pkg['displayName'])}</DisplayName>
    <Description xml:space="preserve">{escape(pkg['description'])}</Description>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{pkg['engines']['vscode']}" />
    </Properties>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
  </Assets>
</PackageManifest>
"""
    types = ('<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension=".json" ContentType="application/json"/><Default Extension=".js" ContentType="application/javascript"/>'
             '<Default Extension=".vsixmanifest" ContentType="text/xml"/><Default Extension=".svg" ContentType="image/svg+xml"/></Types>')
    out = os.path.join(out_dir, f"{pkg['name']}-{pkg['version']}.vsix")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("extension.vsixmanifest", manifest)
        for f in FILES:
            z.write(os.path.join(HERE, f), f"extension/{f}")
        if build_id:
            z.writestr("extension/BUILD", build_id + "\n")
    return out


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else ".", sys.argv[2] if len(sys.argv) > 2 else ""))
