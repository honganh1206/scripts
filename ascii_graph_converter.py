import sys
import os
import io
import numpy as np
import pyperclip
from PIL import Image

def get_clipboard_image():
    """
    Cross-platform method to get image from clipboard
    """
    platform = sys.platform.lower()

    try:
        if platform.startswith('win'):
            from PIL import ImageGrab
            return ImageGrab.grabclipboard()

        elif platform.startswith('darwin'):  # macOS
            from AppKit import NSPasteboard, NSImage
            pasteboard = NSPasteboard.generalPasteboard()
            image_data = pasteboard.dataForType_(NSPasteboard.NSPasteboardTypePNG)
            if image_data:
                return Image.open(io.BytesIO(image_data))

        elif platform.startswith('linux'):
            try:
                from PIL import ImageGrab
                return ImageGrab.grabclipboard()
            except ImportError:
                print("Pillow's ImageGrab might not work on Linux. Install python3-pil.imagegrab if needed.")
                return None

        else:
            print(f"Unsupported platform: {platform}")
            return None

    except Exception as e:
        print(f"Error getting clipboard image: {e}")
        return None

def image_to_ascii_graph(image=None):
    """
    Convert an image to an ASCII representation of its data graph.
    """
    if image is None:
        image = get_clipboard_image()
        if not image:
            return None

    # Convert image to grayscale
    gray_image = image.convert('L')

    # Resize image to a reasonable graph size
    resized_image = gray_image.resize((80, 40))

    # Convert to numpy array
    img_array = np.array(resized_image)

    # Normalize pixel values
    normalized = (img_array - img_array.min()) / (img_array.max() - img_array.min())

    # ASCII characters from sparse to dense
    ascii_chars = ' .:-=+*#%@'

    # Create ASCII graph
    ascii_graph = []
    for row in normalized:
        ascii_row = ''.join([ascii_chars[int(pixel * (len(ascii_chars) - 1))] for pixel in row])
        ascii_graph.append(ascii_row)

    return '\n'.join(ascii_graph)

def main():
    print("Waiting for an image in the clipboard...")

    while True:
        try:
            input("Press Enter to convert clipboard image to ASCII graph (Ctrl+C to exit)...")

            ascii_result = image_to_ascii_graph()

            if ascii_result:
                print("\nASCII Graph:")
                print(ascii_result)
                pyperclip.copy(ascii_result)
                print("\nASCII graph copied to clipboard!")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
