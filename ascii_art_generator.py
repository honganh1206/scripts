from ascii_magic import AsciiArt
import sys

def generate_ascii_art(image_path, width=100, mode='blocks', output_file=None):
    """Generate ASCII art using ascii-magic package
    
    Args:
        image_path: Path to input image
        width: Width in characters (default 100)
        mode: 'blocks' or 'ascii' (default 'blocks')
        output_file: Optional path to save output
    """
    try:
        # Create ASCII art object
        # mode='terminal' gives the best block art
        my_art = AsciiArt.from_image(image_path)
        
        # Generate the art with specified width
        if mode == 'blocks':
            # Terminal mode uses block characters for smooth shading
            art_str = my_art.to_terminal(columns=width)
        else:
            # ASCII mode uses traditional text characters
            art_str = my_art.to_ascii(columns=width)
        
        # Output
        if output_file:
            with open(output_file, "w", encoding='utf-8') as f:
                f.write(art_str)
            print(f"ASCII art saved to {output_file}")
        else:
            print(art_str)
        
        return art_str
        
    except FileNotFoundError:
        print(f"Error: Image file '{image_path}' not found")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def show_colored_art(image_path, width=100):
    """Generate colored ASCII art in terminal"""
    try:
        my_art = AsciiArt.from_image(image_path)
        my_art.to_terminal(columns=width, width_ratio=2)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Example usage
    if len(sys.argv) < 2:
        print("Usage: python script.py <image_path> [width] [mode] [output_file]")
        print("Modes: blocks (default), ascii, color")
        print("\nExamples:")
        print("  python script.py photo.jpg")
        print("  python script.py photo.jpg 80 blocks")
        print("  python script.py photo.jpg 80 ascii output.txt")
        print("  python script.py photo.jpg 100 color")
        sys.exit(1)
    
    image_path = sys.argv[1]
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    mode = sys.argv[3] if len(sys.argv) > 3 else 'blocks'
    output_file = sys.argv[4] if len(sys.argv) > 4 else None
    
    if mode == 'color':
        show_colored_art(image_path, width)
    else:
        generate_ascii_art(image_path, width, mode, output_file)
