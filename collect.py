#!/usr/bin/env python2
# encoding: utf8

import os
from subprocess import Popen, PIPE, check_output
import tempfile
import sys
import sqlite3
from common import *
import re

def collect_dir(top):
  all_files = []
  for root, dirs, files in os.walk(top):
    for f in files:
      if f.lower().endswith('.mkv'):
        all_files.append(os.path.join(root, f))
  for f in sorted(all_files):
    collect_file(f)

def collect_file(file_path):
  if file_path.startswith('./'):
    file_path = file_path[2:]

  cur = db.cursor()
  cur.execute("SELECT COUNT(*) FROM video WHERE path = ? AND collected = 1",
      (file_path.decode('utf8'), ))
  if cur.fetchone()[0] == 1:
    print 'collected', file_path
    return

  md5sum = get_md5sum(file_path)
  video_id = get_video_id(md5sum, file_path)
  print video_id, file_path, md5sum

  out = check_output(['mkvmerge', '-i', file_path])
  tracks = [l for l in out.splitlines() if ': subtitles (S_TEXT' in l]
  assert len(tracks) > 0 # video without subtitle would not be accepted
  for track in tracks:
    collect_track(video_id, file_path, track)

  cur.execute("UPDATE video SET collected=1 WHERE serial = ?", 
      (video_id, ))
  db.commit()

def collect_track(video_id, file_path, track):
  track_id = track.split()[2][:-1]
  out, out_path = tempfile.mkstemp()
  p1 = Popen(['mkvextract', 'tracks', file_path, '%s:%s' % (track_id, out_path)])
  p1.wait()
  with open(out_path, 'r') as out:
    content = out.read()
    sub_type = track[track.index('/') + 1 : track.rindex(')')]
    entries = None
    if sub_type == 'UTF8':
      entries = collect_utf8_sub(content)
    elif sub_type == 'ASS':
      entries = collect_ass_sub(content)
    else:
      unknow_subtitle_type
    cur = db.cursor()
    print len(entries), 'subtitles'
    for start, end, text in entries:
      #print start, end, text
      try:
        cur.execute('INSERT INTO subtitle VALUES (NULL, ?, ?, ?, ?)',
            (video_id, start, end, text))
      except sqlite3.IntegrityError: pass
    db.commit()
    cur.close()

def collect_utf8_sub(content):
  subs = set()
  for block in content.split('\n\n'):
    if len(block) == 0: continue
    lines = block.splitlines()
    if len(lines) < 3:
      print repr(block)
      malform_sub
    start, end = lines[1].split('-->')
    start = start.strip()
    end = end.strip()
    assert start[0].isdigit()
    assert end[0].isdigit()
    start = convert_time(start)
    end = convert_time(end)
    t = ''.join(l.strip() for l in lines[2:]).decode('utf8')
    subs.add((start, end, t))
  return subs

def collect_ass_sub(content):
  subs = set()
  for line in content.splitlines():
    line = line.strip()
    if line.startswith('Dialogue'):
      ss = line.split(',', 10)
      start = ss[1]
      end = ss[2]
      assert start[0].isdigit()
      assert end[0].isdigit()
      start = convert_time(start)
      end = convert_time(end)
      ts = convert_sub(ss[-1].strip().decode('utf8'))
      for t in ts:
        subs.add((start, end, t))
  return subs

def convert_sub(s):
  s = re.sub(r'\{[^}]*?\}', '', s)
  s = re.sub(r'^[0-9].*?\}', '', s)
  ss = s.split(r'\N')
  return ss

def convert_time(s):
  s = s.split(':')
  s[2] = s[2].replace(',', '.')
  milli = int(s[0]) * 3600 * 1000
  milli += int(s[1]) * 60 * 1000
  milli += float(s[2]) * 1000
  return int(milli)

def get_md5sum(file_path):
  p1 = Popen(['head', '-c%d' % (1024 * 1024 * 64), file_path], stdout = PIPE)
  p2 = Popen(['md5sum'], stdin = p1.stdout, stdout = PIPE)
  p1.stdout.close()
  md5sum = p2.communicate()[0].split()[0]
  p3 = Popen(['tail', '-c%d' % (1024 * 1024 * 64), file_path], stdout = PIPE)
  p4 = Popen(['md5sum'], stdin = p3.stdout, stdout = PIPE)
  p3.stdout.close()
  md5sum += p4.communicate()[0].split()[0]
  p2.stdout.close()
  p4.stdout.close()
  return md5sum

def get_video_id(md5sum, file_path):
  file_path = file_path.decode('utf8')
  cur = db.cursor()
  cur.execute('SELECT serial FROM video where md5sum = ?', (md5sum,))
  res = cur.fetchone()
  if res is None: # insert new video
    cur.execute('INSERT INTO video VALUES (NULL, ?, ?, 0)', (md5sum, file_path))
    db.commit()
    return cur.lastrowid
  else:
    return res[0]
  cur.close()

def create_database():
  cur = db.cursor()
  try:
    cur.execute('''CREATE TABLE subtitle (
    serial integer primary key not null,
    video_id int,
    start integer,
    end integer,
    content text,
    unique (video_id, start, end, content)
    )''')
  except sqlite3.OperationalError: pass
  db.commit()
  try:
    cur.execute('''CREATE TABLE video (
    serial integer primary key not null,
    md5sum text,
    path text,
    collected boolean,
    unique (md5sum)
    )''')
    cur.execute('CREATE INDEX md5sum on video (md5sum ASC)')
    cur.execute('CREATE INDEX path on video (path ASC)')
  except sqlite3.OperationalError: pass
  db.commit()
  cur.close()

def clean():
  cur = db.cursor()
  cur.execute("SELECT * FROM video")
  res = cur.fetchall()
  for serial, md5, path, collected in res:
    if not os.path.exists(path):
      print path
      cur.execute("DELETE FROM subtitle WHERE video_id = ?", [serial])
      cur.execute("DELETE FROM video WHERE serial = ?", [serial])
  db.commit()
  cur.close()

def clean_sub():
  cur = db.cursor()
  cur.execute("SELECT * FROM video WHERE path LIKE '%剪刀%'")
  res = cur.fetchall()
  for serial, md5, path, collected in res:
    cur.execute("SELECT * FROM subtitle WHERE video_id = ?", [serial])
    subs = cur.fetchall()
    for sub_id, v_id, start, end, sub in subs:
      print sub
      print re.sub(r'\{[^}]*?\}', '', sub)
      print 
  db.commit()
  cur.close()

def main():
  create_database()
  clean()
  collect_dir('.')

  #clean_sub()

  db.close()

if __name__ == '__main__':
  main()
