from roboflow import Roboflow
import os

def download_model():
    print("Downloading YOLOv8 model from Roboflow...")
    
    # Your Roboflow credentials
    API_KEY = "7XXKW0vrF3KT4OBhRoaw"
    PROJECT = "waste-sorter-tui1u"
    VERSION = "4"
    
    # Create models directory if it doesn't exist
    model_dir = "models"
    if not os.path.exists(model_dir):
        os.makedirs(model_dir)
    
    try:
        from ultralytics import YOLO
        
        # Initialize Roboflow and download YOLOv8 model
        print("\nInitializing YOLOv8 base model...")
        model = YOLO('yolov8n.pt')  # Start with base YOLOv8 nano model
        
        # Export Roboflow model to YOLOv8 format
        print("\nExporting model to YOLOv8 format...")
        export_url = f"https://app.roboflow.com/{PROJECT}/{VERSION}/model"
        print(f"Download your model from: {export_url}")
        print("\nPlease:")
        print("1. Open this URL in your browser")
        print("2. Select 'YOLOv8' format")
        print("3. Download the model")
        print("4. Copy the downloaded .pt file to the 'models' directory as 'yolov8_model.pt'")
        
        return True
        
        response = requests.get(model_url, headers=headers)
        response.raise_for_status()
        
        # Save the model
        model_path = os.path.join(model_dir, "yolov8_model.pt")
        with open(model_path, 'wb') as f:
            f.write(response.content)
            
        if os.path.exists(model_path) and os.path.getsize(model_path) > 0:
            print(f"\nModel downloaded successfully!")
            print(f"Model saved to: {os.path.abspath(model_path)}")
            print(f"File size: {os.path.getsize(model_path) / (1024*1024):.1f} MB")
            return True
        else:
            print("Error: Model file is empty or not found after download")
            return False
            
    except Exception as e:
        print(f"Error downloading model: {e}")
        return False        # Save the model
        model_path = os.path.join(model_dir, "model.pt")
        with open(model_path, 'wb') as f:
            f.write(response.content)
            
        print(f"\nModel downloaded successfully!")
        print(f"Model saved to: {os.path.abspath(model_path)}")
        print(f"File size: {os.path.getsize(model_path) / (1024*1024):.1f} MB")
        
        # List all files in current directory and subdirectories
        print("\nVerifying downloaded model...")
        for root, dirs, files in os.walk("."):
            for file in files:
                if file.endswith(".pt"):
                    found_path = os.path.join(root, file)
                    print(f"Found model file: {found_path}")
                    return True
                    
        print("\nNo .pt files found. Listing directory contents:")
        for root, dirs, files in os.walk("."):
            print(f"\nDirectory: {root}")
            for f in files:
                print(f"  {f}")
            
        return False
            
    except Exception as e:
        print(f"Error downloading model: {e}")
        return False

if __name__ == "__main__":
    download_model()
