#!/usr/bin/python3

# A helper script run by 'create_release.sh' to extract the information of last
# release from CHANGELOG.md and create a 'release' tag in the appdata xml.

import re
from datetime import datetime
import xml.etree.ElementTree as ET
import hashlib
import subprocess
import os.path
HEADER_PT = re.compile(r"##\s+([0-9.]+) - \w+\s+(.+)")
LINE_PT = re.compile(r"\* (.*)")

def extract(changelog):
	in_content = False
	changelogs = []
	release = ""
	date_string = ""
	with open(changelog) as f:
		for line in f:
			if not in_content:
				m = HEADER_PT.match(line)
				if m:
					in_content = True
					release = m.group(1)
					date_string = m.group(2)
			else:
				m = LINE_PT.match(line)
				if m:
					changelogs.append(m.group(1))
				else:
					break
	return release, datetime.strptime(date_string, "%d %b %Y").strftime("%Y-%m-%d"), changelogs

def new_release(release, date, changelogs):
	tag = ET.Element('release')
	tag.set("date", date)
	tag.set("version", release)
	description = ET.SubElement(tag, "description")
	ul = ET.SubElement(description, "ul")
	for entry in changelogs:
			ET.SubElement(ul, "li").text = entry

	#artifacts = ET.SubElement(tag, "artifacts")
	#artifact = ET.SubElement(artifacts, "artifact")
	#artifact.set("type", "source")

	#tarball = "zim-%s.tar.gz" % release
	#ET.SubElement(artifact, "location").text = "http://www.zim-wiki.org/downloads/" + tarball

	#checksum = ET.SubElement(artifact, "checksum")
	#checksum.set("type", "sha256")
	#hasher = hashlib.sha256()
	#with open("dist/" + tarball, "rb") as f:
	#	for chunk in iter(lambda: f.read(4096), b""):
	#		hasher.update(chunk)
	#checksum.text = hasher.hexdigest()

	#size = ET.SubElement(artifact, "size")
	#size.set("type", "download")
	#size.text = str(os.path.getsize("dist/" + tarball))

	return tag


def insert_release(appdata, release_tag):
	appdata_lines = open(appdata).readlines()
	insert_at = appdata_lines.index("  <releases>\n") + 1
	with open(appdata, "w") as f:
		p = subprocess.Popen(["xmllint", "--format", "-"], stdin=subprocess.PIPE, stdout=f)
		for line in appdata_lines[:insert_at]:
			p.stdin.write(line.encode("UTF-8"))
		p.stdin.write(ET.tostring(release_tag))
		for line in appdata_lines[insert_at:]:
			p.stdin.write(line.encode("UTF-8"))
		p.stdin.close()
		p.wait()


def main(changelog, appdata):
	release, date, changelogs = extract(changelog)
	release_tag = new_release(release, date, changelogs)
	insert_release(appdata, release_tag)

if __name__ == '__main__':
	main("CHANGELOG.md", "xdg/org.zim_wiki.Zim.appdata.xml")
