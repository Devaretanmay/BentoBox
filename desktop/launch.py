import os
import webview

def start_window():
    # Resolve the absolute path of index.html in the desktop directory
    dir_path = os.path.dirname(os.path.realpath(__file__))
    html_path = os.path.join(dir_path, "index.html")
    
    # Create the window
    webview.create_window(
        title="Compart Dashboard",
        url=html_path,
        width=1180,
        height=760,
        resizable=True,
        min_size=(900, 650)
    )
    webview.start(debug=True)

if __name__ == "__main__":
    start_window()
