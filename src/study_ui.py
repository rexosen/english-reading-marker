"""Desktop learning dialogs and reader controls."""
from __future__ import annotations
import hashlib
import json
import uuid
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt, QTimer, QSettings, QUrl
from PySide6.QtGui import QColor, QFont, QTextCursor, QTextBlockFormat, QImage, QPainter
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QFileDialog, QMessageBox, QInputDialog, QColorDialog, QWidget)
from PySide6.QtTextToSpeech import QTextToSpeech
from src.domain import python_offset_to_qt, qt_offset_to_python
from src.dictation import compare
from src.listening import ListeningReviews
from src.study import StudyRepository, sentence_ranges
from src.storage import backup_database, backup_details, schedule_restore


class StudyUi:
    def init_study_ui(self):
        self.study = StudyRepository(self.repository)
        self.listening = ListeningReviews(self.repository.database_path.parent / 'listening_reviews.json')
        self.display_settings = QSettings(str(self.repository.database_path.parent / 'display.ini'), QSettings.Format.IniFormat)
        defaults = {'size':18, 'line':160, 'margin':22, 'theme':'paper', 'image':'', 'opacity':22, 'width':1200}
        self.display_options = {key:self.display_settings.value(key, value) for key,value in defaults.items()}
        for key in ('size','line','margin','opacity','width'): self.display_options[key] = int(self.display_options[key])
        self._sentence_active = False
        self._sentence_spoken = False
        self._sentence_index = 0
        self._sentence_round = 0
        self._sentences = []
        self._gap_paused = False
        self.sentence_timer = QTimer(self)
        self.sentence_timer.setSingleShot(True)
        self.sentence_timer.timeout.connect(self._play_sentence)
        self.speech.stateChanged.connect(self._sentence_speech_state)
        self.reader.set_background_options(self.display_options)
        self.apply_display()
        menu = self.menuBar().addMenu('学习与阅读')
        menu.addAction('生词复习卡片', self.open_review)
        menu.addAction('句子收藏与笔记', self.open_notes)
        menu.addAction('听写练习（当前文章）', self.open_dictation)
        menu.addAction('阅读显示与背景图', self.open_display)
        menu.addAction('管理文章分组', self.manage_groups)
        self.reader.sentence_requested.connect(self.play_sentence_at)
        self.refresh_group_filter()

    def add_library_controls(self, layout):
        self.article_search = QLineEdit()
        self.article_search.setPlaceholderText('搜索标题或正文')
        self.article_search.textChanged.connect(lambda: self.refresh_articles(self.current_article_id))
        layout.addWidget(self.article_search)
        row = QHBoxLayout()
        self.group_filter = QComboBox()
        self.group_filter.addItem('全部文章', 'all')
        self.group_filter.currentIndexChanged.connect(lambda: self.refresh_articles(self.current_article_id))
        row.addWidget(self.group_filter, 1)
        group_button = QPushButton('分组')
        group_button.clicked.connect(self.manage_groups)
        row.addWidget(group_button)
        layout.addLayout(row)

    def add_study_controls(self, layout):
        self.sentence_controls = QWidget()
        controls_layout = QVBoxLayout(self.sentence_controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)
        layout.addWidget(self.sentence_controls)
        self.sentence_controls.hide()
        row = QHBoxLayout()
        for title, callback in [('上一句', lambda:self.step_sentence(-1)), ('▶ 逐句', self.start_sentences), ('下一句', lambda:self.step_sentence(1))]:
            button = QPushButton(title); button.clicked.connect(callback); row.addWidget(button)
        self.single_sentence = QCheckBox('只循环当前句')
        row.addWidget(self.single_sentence)
        self.sentence_repeat = QSpinBox(); self.sentence_repeat.setRange(1,99); self.sentence_repeat.setValue(1); self.sentence_repeat.setSuffix(' 遍')
        row.addWidget(self.sentence_repeat)
        self.sentence_gap = QDoubleSpinBox(); self.sentence_gap.setRange(0,30); self.sentence_gap.setSingleStep(0.5); self.sentence_gap.setValue(1); self.sentence_gap.setSuffix(' 秒停顿')
        row.addWidget(self.sentence_gap)
        controls_layout.addLayout(row)
        row2 = QHBoxLayout()
        for title, callback in [('✓ 听懂', lambda: self._mark_sentence('heard')), ('✗ 没听懂', lambda: self._mark_sentence('missed'))]:
            button = QPushButton(title); button.clicked.connect(callback); row2.addWidget(button)
        self.replay_missed = QCheckBox('只重听没听懂句'); self.replay_missed.toggled.connect(self._refresh_listening_label); row2.addWidget(self.replay_missed)
        self.listening_label = QLabel(''); row2.addWidget(self.listening_label); row2.addStretch(1)
        controls_layout.addLayout(row2)
        self.sentence_label = QLabel('双击正文也可从所在句开始逐句朗读；逐句时可用“听懂/没听懂”标记当前句。')
        self.sentence_label.setWordWrap(True)
        controls_layout.addWidget(self.sentence_label)

    def filtered_articles(self):
        articles = self.repository.list_articles()
        if not hasattr(self,'study'): return articles
        query = self.article_search.text().strip().casefold()
        selected_group = self.group_filter.currentData()
        result = []
        items = self.study.items()
        active_groups = self.study.groups()
        sync_ids = dict(self.repository.connection.execute('SELECT article_id,sync_id FROM sync_articles'))
        for a in articles:
            meta = items.get('meta:' + sync_ids[a['id']]) or {'article_id':sync_ids[a['id']], 'group':'', 'pinned':False, 'read':False}
            if query and query not in (a['title']+'\n'+a['text']).casefold(): continue
            group = meta['group'] if meta['group'] in active_groups else ''
            if selected_group == 'ungrouped' and group: continue
            if selected_group not in ('all','ungrouped',None) and group != selected_group: continue
            result.append({**a,'meta':meta})
        return sorted(result,key=lambda a:(not a['meta']['pinned'],-a['id']))

    def article_caption(self, article):
        meta = article.get('meta',{})
        return ('★ ' if meta.get('pinned') else '') + article['title'] + ('  ✓' if meta.get('read') else '')

    def refresh_group_filter(self):
        if not hasattr(self,'study'): return
        selected = self.group_filter.currentData()
        self.group_filter.blockSignals(True)
        self.group_filter.clear(); self.group_filter.addItem('全部文章','all'); self.group_filter.addItem('未分组','ungrouped')
        for key,name in self.study.groups().items(): self.group_filter.addItem(name,key)
        self.group_filter.setCurrentIndex(max(0,self.group_filter.findData(selected)))
        self.group_filter.blockSignals(False)

    def manage_groups(self):
        if not hasattr(self,'study'): return
        dialog = QDialog(self); dialog.setWindowTitle('管理文章分组'); dialog.resize(440,360)
        layout = QVBoxLayout(dialog); listing = QListWidget(); layout.addWidget(listing)
        def refresh():
            listing.clear(); self.refresh_group_filter(); self.refresh_articles(self.current_article_id)
            for key,name in self.study.groups().items():
                item=QListWidgetItem(name);item.setData(Qt.ItemDataRole.UserRole,key);listing.addItem(item)
        def edit(create=False):
            item=listing.currentItem()
            if not create and not item:return
            name,ok=QInputDialog.getText(dialog,'新建分组' if create else '分组改名','分组名称（最多60字）：',text='' if create else item.text())
            if not ok:return
            try:self.study.set('group:'+str(uuid.uuid4()) if create else item.data(Qt.ItemDataRole.UserRole),{'name':name});refresh()
            except ValueError as error:QMessageBox.warning(dialog,'保存失败',str(error))
        def remove():
            item=listing.currentItem()
            if not item:return
            if QMessageBox.question(dialog,'删除分组','仅删除分组，组内文章会显示为未分组。继续？') != QMessageBox.StandardButton.Yes:return
            self.study.set(item.data(Qt.ItemDataRole.UserRole),None);refresh()
        row=QHBoxLayout()
        for title,action in [('新建',lambda:edit(True)),('改名',lambda:edit(False)),('删除',remove)]:
            button=QPushButton(title);button.clicked.connect(action);row.addWidget(button)
        layout.addLayout(row);refresh();dialog.exec()

    def assign_group(self, article_id):
        groups=self.study.groups(); names=['未分组']+list(groups.values())
        meta=self.study.metadata(article_id); keys=['']+list(groups)
        name,ok=QInputDialog.getItem(self,'移动到分组','选择分组：',names,keys.index(meta['group']) if meta['group'] in keys else 0,False)
        if ok:self.study.update_metadata(article_id,group=keys[names.index(name)]);self.refresh_articles(self.current_article_id)

    def toggle_article_flag(self, article_id, field):
        self.study.update_metadata(article_id,**{field:not self.study.metadata(article_id)[field]})
        self.refresh_articles(self.current_article_id)

    def jump_to_range(self, article_id, start, end):
        self.article_search.clear();self.group_filter.setCurrentIndex(0);self.refresh_articles(article_id)
        if self.current_article_id != article_id:return
        text=self.reader.toPlainText();cursor=self.reader.textCursor()
        cursor.setPosition(python_offset_to_qt(text,start));cursor.setPosition(python_offset_to_qt(text,end),QTextCursor.MoveMode.KeepAnchor)
        self.reader.setTextCursor(cursor);self.reader.ensureCursorVisible()

    def open_review(self):
        dialog=QDialog(self);dialog.setWindowTitle('生词复习卡片');dialog.resize(720,560)
        layout=QVBoxLayout(dialog);mode=QComboBox();mode.addItem('到期与未复习的生词',False);mode.addItem('全部生词练习',True);layout.addWidget(mode)
        status=QLabel();layout.addWidget(status)
        word=QLabel();word.setWordWrap(True);word.setStyleSheet('font-size:28pt;font-weight:bold;');layout.addWidget(word)
        source=QLabel();source.setWordWrap(True);layout.addWidget(source)
        content=QTextBrowser();layout.addWidget(content,1)
        row=QHBoxLayout();pronounce=QPushButton('▶ 单词发音');reveal=QPushButton('显示释义');jump=QPushButton('回到原文')
        for button in (pronounce,reveal,jump):row.addWidget(button)
        layout.addLayout(row);rating=QHBoxLayout();buttons=[];session={'queue':[],'card':None,'done':0}
        def load():
            queue=session['queue'];card=queue.pop(0) if queue else None;session['card']=card
            for button in buttons:button.setEnabled(False)
            pronounce.setEnabled(bool(card));reveal.setEnabled(bool(card));jump.setEnabled(bool(card))
            if not card:
                word.setText('本轮复习完成');source.setText('未到期的生词会在到期后出现，也可以切换到全部生词练习。');content.clear();status.setText(f"本轮已复习 {session['done']} 条");return
            word.setText(card['word']);source.setText('来源：'+card['article_title']);content.setPlainText(card['context'])
            status.setText(f"剩余 {len(queue)+1} 条 · 本轮已复习 {session['done']} 条")
        def reset():
            session.update(queue=self.study.review_cards(all_cards=mode.currentData()),done=0);load()
        def show_answer():
            card=session['card']
            if card:content.setPlainText(card['context']+'\n\n中文释义：\n'+card['definition']);[b.setEnabled(True) for b in buttons]
        def grade(value):
            card=session['card']
            if not card:return
            self.study.grade(card,value);session['done']+=1;load()
        for title,value in [('不认识 · 10分钟后','again'),('模糊 · 1天后','hard'),('认识 · 延长间隔','known')]:
            button=QPushButton(title);button.clicked.connect(lambda checked=False,v=value:grade(v));rating.addWidget(button);buttons.append(button)
        layout.addLayout(rating);layout.addWidget(QLabel('认识：首次3天，再次按上次间隔翻倍，最多365天。各设备同步复习结果。'))
        mode.currentIndexChanged.connect(reset);reveal.clicked.connect(show_answer)
        pronounce.clicked.connect(lambda:self._speak(session['card']['word']) if session['card'] else None)
        def go():
            card=session['card']
            if card:dialog.accept();self.jump_to_range(card['article_id'],card['start'],card['end'])
        jump.clicked.connect(go);reset();dialog.exec()

    def save_selected_note(self):
        selected=self._get_translation_selection()
        if selected is None or self.current_article_id is None:return
        start,end,_=selected;translation=self.current_definition if self.definition_selection==selected else ''
        self.edit_note({'local_id':self.current_article_id,'start':start,'end':end,'text':self.reader.toPlainText()[start:end],'translation':translation,'note':''})

    def edit_note(self,record):
        dialog=QDialog(self);dialog.setWindowTitle('句子收藏与笔记');dialog.resize(680,570)
        layout=QVBoxLayout(dialog);original=QTextBrowser();original.setPlainText(record['text']);layout.addWidget(original)
        layout.addWidget(QLabel('中文译文（可自行填写或修改）'));translation=QTextEdit();translation.setPlainText(record.get('translation',''));layout.addWidget(translation)
        layout.addWidget(QLabel('我的笔记'));note=QTextEdit();note.setPlainText(record.get('note',''));layout.addWidget(note)
        save=QPushButton('保存收藏');save.clicked.connect(dialog.accept);layout.addWidget(save)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            try:self.study.save_note(record['local_id'],record['start'],record['end'],translation.toPlainText(),note.toPlainText(),record.get('key'), expected=record.get('_base'));self._show_hint('句子收藏与笔记已保存。')
            except ValueError as error:QMessageBox.warning(self,'保存失败',str(error))

    def open_notes(self):
        dialog=QDialog(self);dialog.setWindowTitle('句子收藏与笔记');dialog.resize(780,650)
        layout=QVBoxLayout(dialog);search=QLineEdit();search.setPlaceholderText('搜索原文、译文、笔记或文章名称');layout.addWidget(search)
        listing=QListWidget();listing.setWordWrap(True);layout.addWidget(listing,1);detail=QTextBrowser();layout.addWidget(detail,1)
        def refresh():
            listing.clear();query=search.text().casefold()
            for record in self.study.notes():
                if query and query not in (record['title']+record['text']+record['translation']+record['note']).casefold():continue
                item=QListWidgetItem(record['title']+' · '+record['text'][:100]);item.setData(Qt.ItemDataRole.UserRole,record);listing.addItem(item)
            if listing.count():listing.setCurrentRow(0)
            else:detail.setPlainText('在正文中选中句段，点击“收藏所选句段”。')
        def current():return listing.currentItem().data(Qt.ItemDataRole.UserRole) if listing.currentItem() else None
        def show():
            r=current()
            if r:detail.setPlainText(r['text']+'\n\n译文：'+r['translation']+'\n\n笔记：'+r['note'])
        def edit():
            if current():self.edit_note(current());refresh()
        def remove():
            r=current()
            if r and QMessageBox.question(dialog,'删除收藏','确定删除这条句子收藏及笔记？')==QMessageBox.StandardButton.Yes:self.study.set(r['key'],None,expected=r.get('_base'));refresh()
        def jump():
            r=current()
            if r:dialog.accept();self.jump_to_range(r['local_id'],r['start'],r['end'])
        row=QHBoxLayout()
        for title,action in [('编辑',edit),('▶ 朗读',lambda:self._speak(current()['text']) if current() else None),('回到原文',jump),('删除',remove)]:
            button=QPushButton(title);button.clicked.connect(action);row.addWidget(button)
        layout.addLayout(row);search.textChanged.connect(refresh);listing.currentItemChanged.connect(show);refresh();dialog.exec()

    def apply_display(self):
        options=self.display_options
        colors={'paper':('#fff9ed','#302b25'),'light':('#ffffff','#203044'),'green':('#e5efdf','#243829'),'dark':('#202733','#dde5f0')}
        background,foreground=colors.get(options['theme'],colors['paper'])
        self.reader.setStyleSheet(f'QTextEdit {{background: transparent; color:{foreground}; border:1px solid #dce4ed; border-radius:12px; padding:{options["margin"]}px; font-family:Georgia,"Times New Roman"; font-size:{options["size"]}pt;}}')
        self.reader.setMaximumWidth(options['width'])
        self.reader.document().setDefaultFont(QFont('Georgia',options['size']))
        cursor=QTextCursor(self.reader.document());cursor.select(QTextCursor.SelectionType.Document)
        block=QTextBlockFormat();block.setLineHeight(options['line'],QTextBlockFormat.LineHeightTypes.ProportionalHeight.value);cursor.mergeBlockFormat(block)
        self.reader.set_background_options({**options,'background':background})

    def open_display(self):
        dialog=QDialog(self);dialog.setWindowTitle('阅读显示与背景图');dialog.resize(520,540);layout=QVBoxLayout(dialog)
        fields={}
        for key,title,low,high in [('size','字号',10,36),('line','行距（百分比）',110,240),('margin','阅读边距',8,100),('opacity','背景图可见度（百分比）',0,65),('width','正文最大宽度（像素）',520,1800)]:
            layout.addWidget(QLabel(title));spin=QSpinBox();spin.setRange(low,high);spin.setValue(self.display_options[key]);fields[key]=spin;layout.addWidget(spin)
        theme=QComboBox()
        for title,value in [('暖纸色','paper'),('白色','light'),('浅绿色','green'),('深色','dark')]:theme.addItem(title,value)
        theme.setCurrentIndex(max(0,theme.findData(self.display_options['theme'])));layout.addWidget(theme)
        selected={'path':self.display_options['image']};image_label=QLabel('已设置背景图' if selected['path'] else '未设置背景图');layout.addWidget(image_label)
        def choose():
            filename,_=QFileDialog.getOpenFileName(dialog,'选择背景图',str(Path.home()),'图片 (*.png *.jpg *.jpeg *.webp *.bmp)')
            if not filename:return
            image=QImage(filename)
            if image.isNull():QMessageBox.warning(dialog,'图片无法读取','请选择有效的图片。');return
            image=image.scaled(1920,1920,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            folder=self.repository.database_path.parent/'backgrounds';folder.mkdir(exist_ok=True)
            target=folder/(hashlib.sha256(Path(filename).read_bytes()).hexdigest()[:24]+'.jpg')
            if not image.save(str(target),'JPG',88):QMessageBox.warning(dialog,'保存失败','无法保存所选背景图。');return
            selected['path']=str(target);image_label.setText('已选择：'+Path(filename).name)
        row=QHBoxLayout();choose_button=QPushButton('选择自己的背景图');choose_button.clicked.connect(choose);row.addWidget(choose_button)
        clear=QPushButton('移除背景图');clear.clicked.connect(lambda:(selected.update(path=''),image_label.setText('未设置背景图')));row.addWidget(clear);layout.addLayout(row)
        layout.addWidget(QLabel('背景图会复制到本机资料目录，移动原图片不会影响阅读。显示设置不跨设备同步。'))
        save=QPushButton('应用并保存');save.clicked.connect(dialog.accept);layout.addWidget(save)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.display_options={**{key:spin.value() for key,spin in fields.items()},'theme':theme.currentData(),'image':selected['path']}
            for key,value in self.display_options.items():self.display_settings.setValue(key,value)
            self.display_settings.sync();self.apply_display()

    def _current_sync_id(self):
        if self.current_article_id is None: return None
        try: return self.study.sync_id(self.current_article_id)
        except (TypeError, IndexError): return None

    def _sentence_order(self):
        """Indices visited by 逐句 playback, honouring the replay-missed filter."""
        if not self._sentences: return []
        if not self.replay_missed.isChecked(): return list(range(len(self._sentences)))
        sync_id = self._current_sync_id()
        if sync_id is None: return list(range(len(self._sentences)))
        missed = {(start, end) for start, end, _ in self.listening.missed(sync_id, self._sentences)}
        order = [i for i, (start, end, _) in enumerate(self._sentences) if (start, end) in missed]
        return order or list(range(len(self._sentences)))

    def _mark_sentence(self, status):
        sync_id = self._current_sync_id()
        if sync_id is None:
            self._show_hint('请先打开一篇文章，再标记听懂或没听懂。'); return
        if not self._sentences:
            self._sentences = sentence_ranges(self.reader.toPlainText())
            offset = qt_offset_to_python(self.reader.toPlainText(), self.reader.textCursor().position())
            self._sentence_index = next((i for i, s in enumerate(self._sentences) if s[1] > offset), 0)
        if not self._sentences: return
        start, end, text = self._sentences[self._sentence_index]
        after = None if self.listening.status(sync_id, start, end, text) == status else status
        self.listening.mark(sync_id, start, end, text, after)
        label = {'heard': '已标记听懂', 'missed': '已标记没听懂', None: '已清除标记'}[after]
        self.sentence_label.setText(f'第 {self._sentence_index+1}/{len(self._sentences)} 句 · {label}')
        self._refresh_listening_label()

    def _refresh_listening_label(self):
        if not hasattr(self, 'listening_label'): return
        sync_id = self._current_sync_id()
        if sync_id is None or not self._sentences:
            self.listening_label.setText(''); return
        missed = len(self.listening.missed(sync_id, self._sentences))
        self.listening_label.setText(f'本篇没听懂 {missed} 句' if missed else '本篇没有待重听句子')

    def start_sentences(self):
        offset=qt_offset_to_python(self.reader.toPlainText(),self.reader.textCursor().position())
        self.play_sentence_at(offset)

    def play_sentence_at(self, offset):
        self.stop_audio();self._sentences=sentence_ranges(self.reader.toPlainText())
        if not self._sentences:return
        self._sentence_index=next((i for i,s in enumerate(self._sentences) if s[1]>offset),len(self._sentences)-1)
        self._sentence_round=0;self._sentence_active=True;self._refresh_listening_label();self._play_sentence()

    def step_sentence(self, direction):
        if not self._sentences:self._sentences=sentence_ranges(self.reader.toPlainText())
        if not self._sentences:return
        order=self._sentence_order()
        position=order.index(self._sentence_index) if self._sentence_index in order else (-1 if direction>0 else len(order))
        next_position=position+direction
        if not 0<=next_position<len(order):return
        self.stop_audio();self._sentence_index=order[next_position];self._sentence_round=0;self._sentence_active=True;self._play_sentence()

    def _play_sentence(self):
        if not self._sentence_active:return
        start,end,text=self._sentences[self._sentence_index]
        extra=QTextEdit.ExtraSelection();extra.cursor=QTextCursor(self.reader.document());extra.cursor.setPosition(python_offset_to_qt(self.reader.toPlainText(),start));extra.cursor.setPosition(python_offset_to_qt(self.reader.toPlainText(),end),QTextCursor.MoveMode.KeepAnchor)
        extra.format.setBackground(QColor('#70ffcc66'));self.reader.setExtraSelections([extra])
        cursor=self.reader.textCursor();scroll=self.reader.verticalScrollBar().value()
        self.reader.setTextCursor(extra.cursor);self.reader.ensureCursorVisible();self.reader.setTextCursor(cursor)
        self.sentence_label.setText(f'第 {self._sentence_index+1}/{len(self._sentences)} 句 · 第 {self._sentence_round+1}/{self.sentence_repeat.value()} 遍')
        self._sentence_spoken=False;self._speak_system(text)

    def _sentence_speech_state(self,state):
        if not self._sentence_active:return
        if state==QTextToSpeech.State.Speaking:self._sentence_spoken=True
        if state==QTextToSpeech.State.Error:self.cancel_sentence_sequence();return
        if state!=QTextToSpeech.State.Ready or not self._sentence_spoken:return
        self._sentence_spoken=False;self._sentence_round+=1
        if self._sentence_round>=self.sentence_repeat.value():
            order=self._sentence_order()
            position=order.index(self._sentence_index) if self._sentence_index in order else -1
            if self.single_sentence.isChecked() or position+1>=len(order):
                self.cancel_sentence_sequence();self.sentence_label.setText('逐句朗读完成');return
            self._sentence_index=order[position+1];self._sentence_round=0
        self.sentence_timer.start(int(self.sentence_gap.value()*1000))

    def cancel_sentence_sequence(self):
        self._sentence_active=False;self._sentence_spoken=False;self._gap_paused=False
        if hasattr(self,'sentence_timer'):self.sentence_timer.stop()
        if hasattr(self,'reader'):self.reader.setExtraSelections([])

    def open_dictation(self):
        sentences = sentence_ranges(self.reader.toPlainText())
        if not sentences:
            self._show_hint('当前没有打开的文章，或文章正文为空。'); return
        offset = qt_offset_to_python(self.reader.toPlainText(), self.reader.textCursor().position())
        state = {'index': next((i for i, s in enumerate(sentences) if s[1] > offset), 0), 'results': []}
        dialog = QDialog(self); dialog.setWindowTitle('听写练习'); dialog.resize(780, 640)
        layout = QVBoxLayout(dialog)
        info = QLabel(); info.setWordWrap(True); layout.addWidget(info)
        typed = QTextEdit(); typed.setPlaceholderText('听一句，敲一句；没听清的词先跳过，对照后再补。'); layout.addWidget(typed, 1)
        feedback = QTextBrowser(); feedback.setOpenExternalLinks(False); layout.addWidget(feedback, 1)
        row = QHBoxLayout()
        for title, callback in [('上一句', lambda: self._dictation_move(dialog, sentences, state, typed, feedback, info, -1)),
                                ('▶ 播放本句', lambda: self._dictation_play(sentences, state)),
                                ('对照答案', lambda: self._dictation_check(sentences, state, typed, feedback, info)),
                                ('下一句 ▶', lambda: self._dictation_move(dialog, sentences, state, typed, feedback, info, 1))]:
            button = QPushButton(title); button.clicked.connect(callback); row.addWidget(button)
        layout.addLayout(row)
        layout.addWidget(QLabel('听写按当前发音语速朗读一遍；先用“逐句 + 只循环当前句”精听，再来这里检验。'))
        self._dictation_show(sentences, state, typed, feedback, info)
        dialog.exec()

    def _dictation_show(self, sentences, state, typed, feedback, info):
        typed.clear(); feedback.clear()
        info.setText(f'第 {state["index"]+1}/{len(sentences)} 句 · 原文已隐藏，播放后听写。')

    def _dictation_play(self, sentences, state):
        self.stop_audio(); self._speak_system(sentences[state['index']][2])

    def _dictation_check(self, sentences, state, typed, feedback, info):
        result = compare(sentences[state['index']][2], typed.toPlainText())
        parts = []
        for word, status in zip(result['expected'], result['statuses']):
            if status == 'ok': parts.append(word)
            elif status == 'wrong': parts.append(f'<b style="color:#c0392b;text-decoration:underline">{word}</b>')
            else: parts.append(f'<b style="color:#c0392b">[{word}]</b>')
        extras = f'<br>多写的词：{" ".join(result["extra"])}' if result['extra'] else ''
        feedback.setHtml('正确答案：' + ' '.join(parts) + extras + f'<br>本句准确率 {result["accuracy"]*100:.0f}%（红=写错，[红]=漏写）')
        state['results'].append(result['accuracy'])
        info.setText(f'第 {state["index"]+1}/{len(sentences)} 句 · 已对照 {len(state["results"])} 句 · 平均准确率 {sum(state["results"])/len(state["results"])*100:.0f}%')

    def _dictation_move(self, dialog, sentences, state, typed, feedback, info, direction):
        target = state['index'] + direction
        if target < 0: return
        if target >= len(sentences):
            if state['results']:
                info.setText(f'全文听写结束 · 已对照 {len(state["results"])} 句 · 平均准确率 {sum(state["results"])/len(state["results"])*100:.0f}%')
            else:
                info.setText('已到最后一句。')
            return
        state['index'] = target; self._dictation_show(sentences, state, typed, feedback, info); self._dictation_play(sentences, state)

    def open_backup_manager(self):
        dialog=QDialog(self);dialog.setWindowTitle('数据与备份恢复');dialog.resize(760,590);layout=QVBoxLayout(dialog)
        label=QLabel('资料位置：'+str(self.repository.database_path.parent)+'\n每天首次打开自动备份；恢复前还会保存当前资料。');label.setWordWrap(True);layout.addWidget(label)
        listing=QListWidget();layout.addWidget(listing,1);detail=QTextBrowser();layout.addWidget(detail,1)
        def add(path):
            try:
                data=backup_details(path);item=QListWidgetItem(f"{data['modified']} · {data['articles']}篇 · {data['annotations']}处划线 · {data['vocabulary']}条生词 · {Path(path).name}")
                item.setData(Qt.ItemDataRole.UserRole,data);listing.addItem(item)
            except Exception:pass
        def refresh():
            listing.clear()
            for path in sorted((self.repository.database_path.parent/'backups').glob('*.sqlite3'),reverse=True):add(path)
            if listing.count():listing.setCurrentRow(0)
        def show():
            item=listing.currentItem()
            if item:
                d=item.data(Qt.ItemDataRole.UserRole);detail.setPlainText('文章：\n'+'\n'.join(d['titles'])+f"\n\n句子收藏 {d['notes']} 条 · 复习记录 {d['reviews']} 条\n"+d['path'])
        def backup():
            try:backup_database(self.repository.database_path);refresh();QMessageBox.information(dialog,'备份完成','当前资料已完整备份。')
            except Exception as error:QMessageBox.warning(dialog,'备份失败',str(error))
        def choose():
            filename,_=QFileDialog.getOpenFileName(dialog,'选择阅读器备份',str(Path.home()),'阅读器数据库 (*.sqlite3)')
            if filename:
                try:backup_details(filename);add(filename);listing.setCurrentRow(listing.count()-1)
                except Exception as error:QMessageBox.warning(dialog,'无法读取',str(error))
        def restore():
            item=listing.currentItem()
            if not item:return
            d=item.data(Qt.ItemDataRole.UserRole)
            question=f"恢复为这份备份？\n{d['articles']}篇文章、{d['annotations']}处划线、{d['vocabulary']}条生词、{d['notes']}条收藏。\n\n会先备份当前资料，然后退出。再次从桌面打开时完成恢复。\n手机尚未同步的修改以后仍可能补传，请先确认手机上的资料。"
            if QMessageBox.question(dialog,'确认恢复并退出',question,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
            try:
                self.stop_audio()
                if self.sync_service:self.sync_service.stop()
                schedule_restore(Path(d['path']),self.repository.database_path)
            except Exception as error:QMessageBox.warning(dialog,'恢复未执行',str(error));return
            dialog.accept();self.close();self.application_quit()
        row=QHBoxLayout()
        for title,action in [('立即备份',backup),('选择备份文件',choose),('恢复所选并退出',restore)]:
            button=QPushButton(title);button.clicked.connect(action);row.addWidget(button)
        layout.addLayout(row);listing.currentItemChanged.connect(show);refresh();dialog.exec()

    def application_quit(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()
