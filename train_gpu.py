from ultralytics import YOLO
import torch

def main():
    # Check GPU availability
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    # Load a new YOLO model
    model = YOLO('yolov8n.yaml')  # create a new YOLO model from scratch
    
    # Train the model with GPU optimizations
    print("Starting training...")
    results = model.train(
        data='dataset/data.yaml',
        epochs=100,  # number of epochs
        imgsz=640,  # image size
        batch=16,    # batch size for 1660S (adjust if needed)
        device=0,    # use GPU
        workers=8,   # number of worker threads
        optimizer='auto',  # automatically select optimizer
        name='waste_sorter',  # save to runs/detect/waste_sorter
        pretrained=False,    # start from scratch
        patience=50,         # early stopping patience
        amp=True,           # automatic mixed precision for faster training
        verbose=True        # show detailed progress
    )
    
    print("Training completed. Model saved in runs/detect/waste_sorter")
    
    # Validate the model
    print("Running validation...")
    results = model.val()
    
    # Export the model to ONNX format for deployment
    print("Exporting model...")
    success = model.export(format='onnx')
    if success:
        print("Model exported successfully to ONNX format")
    else:
        print("Error exporting model")

if __name__ == "__main__":
    main()
