from ultralytics import YOLO
import torch

def main():
    # Load a new YOLO model
    model = YOLO('yolov8n.yaml')  # create a new YOLO model from scratch
    
    # Training arguments
    args = {
        'data': 'dataset/data.yaml',
        'epochs': 100,
        'imgsz': 640,
        'batch': 16,
        'name': 'waste_sorter',
        'device': 'cuda' if torch.cuda.is_available() else 'cpu',
        'workers': 4,
        'patience': 50,  # early stopping patience
        'save': True,    # save checkpoints
        'cache': True,   # cache images for faster training
    }
    
    # Train the model
    print(f"Starting training on {args['device']}...")
    results = model.train(**args)
    
    print("Training completed. Model saved in runs/detect/waste_sorter")

if __name__ == "__main__":
    main()
