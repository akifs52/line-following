# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'mainwindow.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPushButton, QSizePolicy,
    QSpacerItem, QStackedWidget, QStatusBar, QVBoxLayout,
    QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(800, 600)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.centralwidget.setStyleSheet(u"/* ANA GRADIENT */\n"
"QWidget{\n"
"    background: qlineargradient(\n"
"        x1:0, y1:0, x2:1, y2:0,\n"
"        stop:0 rgba(5, 10, 30, 255),\n"
"        stop:1 rgba(40, 80, 160, 255)\n"
"    );\n"
"}\n"
"\n"
"/* FRAME */\n"
"QFrame {\n"
"    background: transparent;\n"
"    border-radius: 10px;\n"
"}\n"
"\n"
"QFrame:hover {\n"
"    background: rgba(0, 0, 0, 50);\n"
"}\n"
"\n"
"/* CAM FRAME */\n"
"QFrame#glassFrame {\n"
"    background: rgba(255, 255, 255, 30);\n"
"    border: 1px solid rgba(255,255,255,80);\n"
"}\n"
"\n"
"/* BUTON */\n"
"QPushButton {\n"
"    background: rgba(10, 20, 50, 200);\n"
"    color: #e6ecff;\n"
"    border: 2px solid rgba(80, 140, 255, 180);\n"
"    border-radius: 10px;\n"
"    padding: 8px 16px;\n"
"}\n"
"\n"
"QPushButton:hover {\n"
"    border: 2px solid rgba(120, 180, 255, 255);\n"
"}\n"
"\n"
"QPushButton:pressed {\n"
"    background: rgba(5, 10, 30, 230);\n"
"}\n"
"\n"
"QLineEdit {\n"
"    background: rgba(255, 255, 255, 25);\n"
"    color: #eaf0ff;\n"
"\n"
"    border: 1px s"
                        "olid rgba(255, 255, 255, 60);\n"
"    border-radius: 10px;\n"
"\n"
"    padding: 8px 12px;\n"
"    selection-background-color: rgba(100, 150, 255, 120);\n"
"}\n"
"\n"
"QLineEdit:hover {\n"
"    border: 1px solid rgba(120, 180, 255, 140);\n"
"}\n"
"\n"
"QLineEdit:focus {\n"
"    background: rgba(255, 255, 255, 40);\n"
"    border: 1px solid rgba(120, 180, 255, 220);\n"
"}\n"
"\n"
"QLineEdit::placeholder {\n"
"    color: rgba(230, 235, 255, 120);\n"
"}\n"
"")
        self.horizontalLayout = QHBoxLayout(self.centralwidget)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.stackedWidget = QStackedWidget(self.centralwidget)
        self.stackedWidget.setObjectName(u"stackedWidget")
        self.mainPage = QWidget()
        self.mainPage.setObjectName(u"mainPage")
        self.horizontalLayout_2 = QHBoxLayout(self.mainPage)
        self.horizontalLayout_2.setSpacing(0)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.horizontalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.frame = QFrame(self.mainPage)
        self.frame.setObjectName(u"frame")
        self.frame.setMaximumSize(QSize(700, 16777215))
        self.frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout = QVBoxLayout(self.frame)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.frame_6 = QFrame(self.frame)
        self.frame_6.setObjectName(u"frame_6")
        self.frame_6.setStyleSheet(u"QFrame\n"
"{\n"
"	border: 2px solid white; \n"
"	border-radius: 10px;	\n"
"}\n"
"\n"
"QFrame:hover\n"
"{\n"
"	border: 2px solid red;\n"
"	border-radius: 10px;\n"
"}")
        self.frame_6.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_6.setFrameShadow(QFrame.Shadow.Raised)
        self.horizontalLayout_5 = QHBoxLayout(self.frame_6)
        self.horizontalLayout_5.setSpacing(0)
        self.horizontalLayout_5.setObjectName(u"horizontalLayout_5")
        self.horizontalLayout_5.setContentsMargins(0, 0, 0, 0)
        self.CamLabel = QLabel(self.frame_6)
        self.CamLabel.setObjectName(u"CamLabel")
        self.CamLabel.setMinimumSize(QSize(0, 0))
        self.CamLabel.setStyleSheet(u"QLabel{\n"
"\n"
"	background-color: rgb(0, 0, 0);\n"
"}")

        self.horizontalLayout_5.addWidget(self.CamLabel)


        self.verticalLayout.addWidget(self.frame_6)

        self.frame_3 = QFrame(self.frame)
        self.frame_3.setObjectName(u"frame_3")
        self.frame_3.setMinimumSize(QSize(0, 0))
        self.frame_3.setMaximumSize(QSize(16777215, 150))
        self.frame_3.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_3.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout_2 = QVBoxLayout(self.frame_3)
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.frame_4 = QFrame(self.frame_3)
        self.frame_4.setObjectName(u"frame_4")
        self.frame_4.setStyleSheet(u"QFrame {\n"
"    background: transparent;\n"
"    border-radius: 10px;\n"
"    transition: none;\n"
"}\n"
"\n"
"QFrame:hover {\n"
"    background: rgba(0, 0, 0, 50); /* hover\u2019da kararma */\n"
"}")
        self.frame_4.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_4.setFrameShadow(QFrame.Shadow.Raised)
        self.horizontalLayout_3 = QHBoxLayout(self.frame_4)
        self.horizontalLayout_3.setSpacing(5)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.horizontalLayout_3.setContentsMargins(0, 0, 0, 0)
        self.frame_7 = QFrame(self.frame_4)
        self.frame_7.setObjectName(u"frame_7")
        self.frame_7.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_7.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout_4 = QVBoxLayout(self.frame_7)
        self.verticalLayout_4.setSpacing(5)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.verticalLayout_4.setContentsMargins(0, 0, 0, 0)
        self.ipLineEdit = QLineEdit(self.frame_7)
        self.ipLineEdit.setObjectName(u"ipLineEdit")
        self.ipLineEdit.setMaximumSize(QSize(16777215, 16777215))
        self.ipLineEdit.setStyleSheet(u"QLineEdit\n"
"{\n"
"	\n"
"	color: rgb(255, 255, 255);\n"
"}")

        self.verticalLayout_4.addWidget(self.ipLineEdit)


        self.horizontalLayout_3.addWidget(self.frame_7)

        self.frame_8 = QFrame(self.frame_4)
        self.frame_8.setObjectName(u"frame_8")
        self.frame_8.setMaximumSize(QSize(80, 16777215))
        self.frame_8.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_8.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout_3 = QVBoxLayout(self.frame_8)
        self.verticalLayout_3.setSpacing(5)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.verticalLayout_3.setContentsMargins(0, 3, 0, 0)
        self.camPortLine = QLineEdit(self.frame_8)
        self.camPortLine.setObjectName(u"camPortLine")
        self.camPortLine.setMaximumSize(QSize(70, 16777215))
        self.camPortLine.setStyleSheet(u"QLineEdit\n"
"{\n"
"	\n"
"	color: rgb(255, 255, 255);\n"
"}")

        self.verticalLayout_3.addWidget(self.camPortLine)

        self.raspiPortLine = QLineEdit(self.frame_8)
        self.raspiPortLine.setObjectName(u"raspiPortLine")
        self.raspiPortLine.setMaximumSize(QSize(70, 16777215))
        self.raspiPortLine.setStyleSheet(u"QLineEdit\n"
"{\n"
"	\n"
"	color: rgb(255, 255, 255);\n"
"}")

        self.verticalLayout_3.addWidget(self.raspiPortLine)


        self.horizontalLayout_3.addWidget(self.frame_8)

        self.tcpCamBtn = QPushButton(self.frame_4)
        self.tcpCamBtn.setObjectName(u"tcpCamBtn")
        self.tcpCamBtn.setMinimumSize(QSize(0, 0))
        self.tcpCamBtn.setMaximumSize(QSize(16777215, 16777215))
        self.tcpCamBtn.setStyleSheet(u"QPushButton {\n"
"    background: rgba(10, 20, 50, 200);\n"
"    color: #e6ecff;\n"
"\n"
"    border: 2px solid rgba(80, 140, 255, 180);\n"
"    border-radius: 10px;\n"
"\n"
"    padding: 8px 16px;\n"
"}\n"
"\n"
"QPushButton:hover {\n"
"    border: 2px solid rgba(120, 180, 255, 255);\n"
"    background: rgba(15, 30, 70, 220);\n"
"}\n"
"\n"
"QPushButton:pressed {\n"
"    background: rgba(5, 10, 30, 230);\n"
"    border: 2px solid rgba(60, 120, 220, 200);\n"
"}")

        self.horizontalLayout_3.addWidget(self.tcpCamBtn)

        self.closeCam = QPushButton(self.frame_4)
        self.closeCam.setObjectName(u"closeCam")

        self.horizontalLayout_3.addWidget(self.closeCam)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_3.addItem(self.horizontalSpacer)


        self.verticalLayout_2.addWidget(self.frame_4)

        self.frame_5 = QFrame(self.frame_3)
        self.frame_5.setObjectName(u"frame_5")
        self.frame_5.setStyleSheet(u"QFrame {\n"
"    background: transparent;\n"
"    border-radius: 10px;\n"
"    transition: none;\n"
"}\n"
"\n"
"QFrame:hover {\n"
"    background: rgba(0, 0, 0, 50); /* hover\u2019da kararma */\n"
"}")
        self.frame_5.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_5.setFrameShadow(QFrame.Shadow.Raised)
        self.horizontalLayout_4 = QHBoxLayout(self.frame_5)
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.otonoumBtn = QPushButton(self.frame_5)
        self.otonoumBtn.setObjectName(u"otonoumBtn")
        self.otonoumBtn.setMinimumSize(QSize(0, 0))
        self.otonoumBtn.setStyleSheet(u"QPushButton {\n"
"    background: rgba(10, 20, 50, 200);\n"
"    color: #e6ecff;\n"
"\n"
"    border: 2px solid rgba(80, 140, 255, 180);\n"
"    border-radius: 10px;\n"
"\n"
"    padding: 8px 16px;\n"
"}\n"
"\n"
"QPushButton:hover {\n"
"    border: 2px solid rgba(120, 180, 255, 255);\n"
"    background: rgba(15, 30, 70, 220);\n"
"}\n"
"\n"
"QPushButton:pressed {\n"
"    background: rgba(5, 10, 30, 230);\n"
"    border: 2px solid rgba(60, 120, 220, 200);\n"
"}")
        self.otonoumBtn.setIconSize(QSize(30, 30))

        self.horizontalLayout_4.addWidget(self.otonoumBtn)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_4.addItem(self.horizontalSpacer_2)


        self.verticalLayout_2.addWidget(self.frame_5)


        self.verticalLayout.addWidget(self.frame_3)


        self.horizontalLayout_2.addWidget(self.frame)

        self.frame_2 = QFrame(self.mainPage)
        self.frame_2.setObjectName(u"frame_2")
        self.frame_2.setMinimumSize(QSize(300, 0))
        self.frame_2.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_2.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout_5 = QVBoxLayout(self.frame_2)
        self.verticalLayout_5.setSpacing(0)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.verticalLayout_5.setContentsMargins(0, 0, 0, 0)
        self.frame_9 = QFrame(self.frame_2)
        self.frame_9.setObjectName(u"frame_9")
        self.frame_9.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_9.setFrameShadow(QFrame.Shadow.Raised)
        self.horizontalLayout_6 = QHBoxLayout(self.frame_9)
        self.horizontalLayout_6.setSpacing(0)
        self.horizontalLayout_6.setObjectName(u"horizontalLayout_6")
        self.horizontalLayout_6.setContentsMargins(0, 0, 0, 0)
        self.quickWidgetSlider1 = QQuickWidget(self.frame_9)
        self.quickWidgetSlider1.setObjectName(u"quickWidgetSlider1")
        self.quickWidgetSlider1.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)

        self.horizontalLayout_6.addWidget(self.quickWidgetSlider1)


        self.verticalLayout_5.addWidget(self.frame_9)

        self.frame_10 = QFrame(self.frame_2)
        self.frame_10.setObjectName(u"frame_10")
        self.frame_10.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_10.setFrameShadow(QFrame.Shadow.Raised)
        self.horizontalLayout_7 = QHBoxLayout(self.frame_10)
        self.horizontalLayout_7.setObjectName(u"horizontalLayout_7")

        self.verticalLayout_5.addWidget(self.frame_10)

        self.frame_11 = QFrame(self.frame_2)
        self.frame_11.setObjectName(u"frame_11")
        self.frame_11.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_11.setFrameShadow(QFrame.Shadow.Raised)

        self.verticalLayout_5.addWidget(self.frame_11)


        self.horizontalLayout_2.addWidget(self.frame_2)

        self.stackedWidget.addWidget(self.mainPage)
        self.page_2 = QWidget()
        self.page_2.setObjectName(u"page_2")
        self.stackedWidget.addWidget(self.page_2)

        self.horizontalLayout.addWidget(self.stackedWidget)

        MainWindow.setCentralWidget(self.centralwidget)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)
        self.tcpCamBtn.clicked.connect(self.closeCam.show)
        self.tcpCamBtn.clicked.connect(self.tcpCamBtn.hide)
        self.closeCam.clicked.connect(self.tcpCamBtn.show)
        self.closeCam.clicked.connect(self.closeCam.hide)

        self.stackedWidget.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.CamLabel.setText("")
        self.ipLineEdit.setPlaceholderText(QCoreApplication.translate("MainWindow", u"ip", None))
        self.camPortLine.setText("")
        self.camPortLine.setPlaceholderText(QCoreApplication.translate("MainWindow", u"cam port", None))
        self.raspiPortLine.setPlaceholderText(QCoreApplication.translate("MainWindow", u"raspi port", None))
        self.tcpCamBtn.setText(QCoreApplication.translate("MainWindow", u"TCP/Cam", None))
        self.closeCam.setText(QCoreApplication.translate("MainWindow", u"Kapat", None))
        self.otonoumBtn.setText(QCoreApplication.translate("MainWindow", u"Otonom S\u00fcr\u00fc\u015f\u00fc Ba\u015flat", None))
    # retranslateUi

