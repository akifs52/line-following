# -*- coding: utf-8 -*-

## Form generated from reading UI file 'loading_dialog.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!

from PySide6 import QtCore, QtGui, QtWidgets

class Ui_LoadingDialog(object):
    def setupUi(self, LoadingDialog):
        LoadingDialog.setObjectName("LoadingDialog")
        LoadingDialog.resize(450, 300)
        LoadingDialog.setMinimumSize(QtCore.QSize(450, 300))
        LoadingDialog.setMaximumSize(QtCore.QSize(450, 300))
        LoadingDialog.setModal(True)
        LoadingDialog.setStyleSheet("QDialog {\n"
"    background-color: #111827;\n"
"    border-radius: 8px;\n"
"    border: 1px solid #374151;\n"
"}")

        self.verticalLayout = QtWidgets.QVBoxLayout(LoadingDialog)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)

        self.contentWidget = QtWidgets.QWidget(LoadingDialog)
        self.contentWidget.setObjectName("contentWidget")
        self.contentLayout = QtWidgets.QVBoxLayout(self.contentWidget)
        self.contentLayout.setSpacing(32)
        self.contentLayout.setContentsMargins(32, 32, 32, 32)

        self.loading_label = QtWidgets.QLabel(self.contentWidget)
        self.loading_label.setMinimumSize(QtCore.QSize(48, 48))
        self.loading_label.setMaximumSize(QtCore.QSize(48, 48))
        self.loading_label.setAlignment(QtCore.Qt.AlignCenter)
        self.loading_label.setObjectName("loading_label")
        self.contentLayout.addWidget(self.loading_label)

        self.textWidget = QtWidgets.QWidget(self.contentWidget)
        self.textWidget.setObjectName("textWidget")
        self.textLayout = QtWidgets.QVBoxLayout(self.textWidget)
        self.textLayout.setSpacing(8)

        self.message_label = QtWidgets.QLabel(self.textWidget)
        self.message_label.setStyleSheet("color: #F9FAFB;\n"
"font-size: 15px;\n"
"font-weight: normal;")
        self.message_label.setAlignment(QtCore.Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setObjectName("message_label")
        self.textLayout.addWidget(self.message_label)

        self.info_label = QtWidgets.QLabel(self.textWidget)
        self.info_label.setStyleSheet("color: #9CA3AF;\n"
"font-size: 12px;")
        self.info_label.setAlignment(QtCore.Qt.AlignCenter)
        self.info_label.setWordWrap(True)
        self.info_label.setObjectName("info_label")
        self.textLayout.addWidget(self.info_label)

        self.contentLayout.addWidget(self.textWidget)

        self.verticalLayout.addWidget(self.contentWidget)

        self.statusWidget = QtWidgets.QWidget(LoadingDialog)
        self.statusWidget.setMinimumSize(QtCore.QSize(0, 36))
        self.statusWidget.setMaximumSize(QtCore.QSize(16777215, 36))
        self.statusWidget.setStyleSheet("QWidget#statusWidget {\n"
"    background-color: #1F2937;\n"
"    border-top: 1px solid #374151;\n"
"}")
        self.statusWidget.setObjectName("statusWidget")
        self.statusLayout = QtWidgets.QHBoxLayout(self.statusWidget)
        self.statusLayout.setSpacing(8)
        self.statusLayout.setContentsMargins(16, 8, 16, 8)

        self.status_indicator = QtWidgets.QLabel(self.statusWidget)
        self.status_indicator.setMinimumSize(QtCore.QSize(8, 8))
        self.status_indicator.setMaximumSize(QtCore.QSize(8, 8))
        self.status_indicator.setStyleSheet("background-color: #3B82F6; \n"
"border-radius: 4px;")
        self.status_indicator.setText("")
        self.status_indicator.setObjectName("status_indicator")
        self.statusLayout.addWidget(self.status_indicator)

        self.status_label = QtWidgets.QLabel(self.statusWidget)
        self.status_label.setStyleSheet("color: #9CA3AF; \n"
"font-size: 11px; \n"
"font-weight: 600;\n"
"text-transform: uppercase;\n"
"letter-spacing: 1px;")
        self.status_label.setObjectName("status_label")
        self.statusLayout.addWidget(self.status_label)

        self.horizontalSpacer_2 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.statusLayout.addItem(self.horizontalSpacer_2)

        self.verticalLayout.addWidget(self.statusWidget)

        self.retranslateUi(LoadingDialog)
        QtCore.QMetaObject.connectSlotsByName(LoadingDialog)

    def retranslateUi(self, LoadingDialog):
        _translate = QtCore.QCoreApplication.translate
        LoadingDialog.setWindowTitle(_translate("LoadingDialog", "Yükleniyor..."))
        self.message_label.setText(_translate("LoadingDialog", "Kamera ve bağlantılar başlatılıyor..."))
        self.info_label.setText(_translate("LoadingDialog", "Lütfen cihazın takılı olduğundan emin olun"))
        self.status_label.setText(_translate("LoadingDialog", "SİSTEM HAZIRLANIYOR"))

if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    LoadingDialog = QtWidgets.QDialog()
    ui = Ui_LoadingDialog()
    ui.setupUi(LoadingDialog)
    LoadingDialog.show()
    sys.exit(app.exec_())
