import FreeCAD as App
import FreeCADGui as Gui
from PySide.QtCore import QTimer
from PySide.QtGui import QColor

def run():
    def dump():
        mw = Gui.getMainWindow()
        prefs = App.ParamGet("User parameter:BaseApp/Preferences/MainWindow")
        print("StyleSheet", prefs.GetString("StyleSheet"))
        print("Theme", prefs.GetString("Theme"))
        g = App.ParamGet("User parameter:BaseApp/Preferences/Themes/UserTokens/")
        for entry in g.GetContents() or []:
            print("ENTRY", entry)
        for key in ["GeneralBackgroundColor","TextForegroundColor","GeneralBorderColor","GeneralBackgroundHoverColor","MenuBackgroundColor"]:
            v = g.GetUnsigned(key, 0)
            c1 = QColor.fromRgba(v)
            r,g_,b,a = (v>>24)&255,(v>>16)&255,(v>>8)&255,v&255
            print(f"{key}: raw={v:#010x} fromRgba={c1.name()} a={c1.alpha()} packedRRGGBBAA=#{r:02x}{g_:02x}{b:02x} aa={a}")
        QTimer.singleShot(200, mw.close)
    QTimer.singleShot(400, dump)
run()
