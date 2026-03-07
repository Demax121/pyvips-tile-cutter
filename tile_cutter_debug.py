"""Debug launcher that shows a console window with error messages for the frozen app."""
import sys
import traceback

def main():
    try:
        # Import and run the main application
        import tile_cutter
        tile_cutter.main()
    except Exception as e:
        # Print full traceback to console
        print("\n" + "="*70)
        print("CRITICAL ERROR - APPLICATION CRASHED")
        print("="*70)
        traceback.print_exc()
        print("="*70)
        print("\nPress Enter to exit...")
        input()
        sys.exit(1)

if __name__ == "__main__":
    main()
