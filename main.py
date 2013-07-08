#!/usr/bin/env python2
# coding: utf8

from PyQt4.QtGui import *
from PyQt4.QtCore import *
import sys
from layout_helper import *
import sqlite3
import itertools
import os
from subprocess import Popen, PIPE

DB = sqlite3.connect('db.sqlite')

BG1 = QBrush(QColor('#FFF'))
BG2 = QBrush(QColor('#DDD'))

class Main(QWidget):
  def __init__(self):
    super(QWidget, self).__init__()

    # search
    self.searchEdit = searchEdit = QLineEdit()
    searchEdit.returnPressed.connect(self.search)
    searchButton = QPushButton('Search')
    searchButton.clicked.connect(self.search)
    self.searchResult = searchResult = QListWidget()
    searchResult.currentRowChanged.connect(self.play)
    font = searchResult.font()
    font.setPointSize(16)
    searchResult.setFont(font)
    self.resultGroups = None

    # play
    self.videoPaths = {}
    self.infoArea = infoArea = QLabel()
    infoArea.setAlignment(Qt.AlignCenter)
    infoArea.setStyleSheet('''QLabel { 
        background-color: #000; color: #FFF; 
        padding-bottom: 30px;
        font-size: 28px; }''')
    infoArea.setTextInteractionFlags(Qt.TextSelectableByMouse)

    self.pathInfo = pathInfo = QLabel()
    pathInfo.setStyleSheet('''QLabel { 
        background-color: #000; color: #FFF; 
        padding-bottom: 5px;
        font-size: 14px; }''')
    pathInfo.setAlignment(Qt.AlignCenter)

    self.vlc = vlc = QWidget()
    vlc.setStyleSheet('''QWidget {
      background-color: #000;
      }''')
    self.control = None

    self.setLayout(
        H( # main box
          V(1, # left panel
            H(searchEdit, searchButton),
            searchResult,
            ),
          V(3, # right panel
            (vlc, 1),
            self.infoArea,
            pathInfo,
            ),
          ))

  def search(self):
    key = self.searchEdit.text().trimmed()
    if len(key) == 0: return
    result = self.searchSubtitle(key)
    self.resultGroups = []
    self.searchResult.clear()
    currentBrush = BG1
    for key, group in result:
      texts = []
      video_id = start = end = None
      for row in group:
        serial, video_id, start, end, text = row
        texts.append(text)
      self.resultGroups.append((video_id, start, end, texts))
      item = QListWidgetItem('\n'.join(texts))
      item.setBackground(currentBrush)
      currentBrush = BG1 if currentBrush == BG2 else BG2
      self.searchResult.addItem(item)
    self.searchResult.scrollToItem(self.searchResult.item(0))

  def play(self, row):
    if row < 0: return
    video_id, start, end, subtitles = self.resultGroups[row]
    video_path = self.getVideoPath(video_id)
    self.infoArea.setText('\n'.join(subtitles))
    self.pathInfo.setText(os.path.basename(video_path))
    self.current_video_path = video_path
    self.current_start = start / 1000.0 - 0.5
    self.current_end = end / 1000.0 + 0.5
    self.startVlc()

  def stopVlc(self):
    if self.control is not None:
      self.control.stdin.write('quit\n')
    self.control = None

  def startVlc(self):
    self.stopVlc()
    self.control = Popen(['vlc', '-Irc',
      '--volume', '196',
      '--quiet',
      '--no-spu',
      '--start-time', str(self.current_start),
      '--stop-time', str(self.current_end),
      '--repeat',
      '--no-video-title-show',
      '--input-fast-seek',
      '--drawable-xid', str(self.vlc.winId()),
      self.current_video_path], stdin = PIPE, stdout = PIPE)

  def getVideoPath(self, video_id):
    path = self.videoPaths.get(video_id, None)
    if path is None:
      cur = DB.cursor()
      cur.execute("SELECT path FROM video WHERE serial = ?",
          (video_id,))
      path = cur.fetchone()[0]
      self.videoPaths[video_id] = path
    return path

  def searchSubtitle(self, key):
    conditions = []
    for key in unicode(key).split('|'):
      words = [w.strip() for w in key.split()]
      permus = list(itertools.permutations(words))
      permus = ['%'.join(x) for x in permus]
      conditions += permus
    condition = ' OR '.join("content LIKE '%%%s%%'" % x
        for x in conditions)
    cur = DB.cursor()
    cur.execute("""SELECT a.*
      FROM subtitle a
      JOIN (SELECT DISTINCT video_id, start
      FROM subtitle
      WHERE %s) b
      ON a.video_id=b.video_id AND a.start=b.start
      ORDER BY a.video_id DESC, a.start ASC
      """ %(
        condition))
    result = cur.fetchall()
    result = itertools.groupby(result, lambda row: (row[1], row[2] / 1000))
    return result

  def keyPressEvent(self, event):
    if event.key() == Qt.Key_Left:
      self.current_start -= 0.2
      self.startVlc()
    elif event.key() == Qt.Key_Right:
      self.current_start += 0.2
      self.startVlc()
    elif event.key() == Qt.Key_Escape:
      self.stopVlc()

def main():
  app = QApplication(sys.argv)
  m = Main()
  m.show()
  sys.exit(app.exec_())

if __name__ == '__main__':
  main()
