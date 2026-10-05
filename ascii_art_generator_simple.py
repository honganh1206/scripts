from PIL import Image
import sys

# ASCII characters ordered by density (darkest to lightest)
ASCII_CHARS = ["@", "#", "S", "%", "?", "*", "+", ";", ":", ",", "."]

def resize_image(img, new_width=100):
    """Resize image maintaining aspect ratio"""
    width, height = img.size
    aspect_ratio = height / width
    new_height = int(new_width * aspect_ratio * 0.55)  # 0.55 adjusts for character height
    return img.resize((new_width, new_height))

def grayscale(img):
    """Convert image to grayscale"""
    return img.convert("L")

def pixels_to_ascii(img):
    """Map pixel brightness to ASCII characters"""
    pixels = img.getdata()
    ascii_str = ""
    for pixel in pixels:
        # Map 0-255 brightness to ASCII character index
        ascii_str += ASCII_CHARS[pixel * len(ASCII_CHARS) // 256]
    return ascii_str

def generate_ascii_art(image_path, width=100, output_file=None):
    """Main function to generate ASCII art from image"""
    try:
        # Load and process image
        img = Image.open(image_path)
        img = resize_image(img, width)
        img = grayscale(img)
        
        # Convert to ASCII
        ascii_str = pixels_to_ascii(img)
        
        # Format into lines
        img_width = img.size[0]
        ascii_art = "\n".join([ascii_str[i:i+img_width] 
                               for i in range(0, len(ascii_str), img_width)])
        
        # Output
        if output_file:
            with open(output_file, "w") as f:
                f.write(ascii_art)
            print(f"ASCII art saved to {output_file}")
        else:
            print(ascii_art)
        
        return ascii_art
        
    except FileNotFoundError:
        print(f"Error: Image file '{image_path}' not found")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    # Example usage
    if len(sys.argv) < 2:
        print("Usage: python script.py <image_path> [width] [output_file]")
        print("Example: python script.py photo.jpg 80 output.txt")
        sys.exit(1)
    
    image_path = sys.argv[1]
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    output_file = sys.argv[3] if len(sys.argv) > 3 else None
    
    generate_ascii_art(image_path, width, output_file)