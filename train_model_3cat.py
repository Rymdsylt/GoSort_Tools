from ultralytics import YOLO

def main():
    # Load a new YOLO model
    model = YOLO('yolov8n.yaml')  # create a new YOLO model from scratch
    
    # Train the model
    print("Starting training...")
    results = model.train(
        data='Waste_Sorter_ToTrain/data_categorized.yaml',
        epochs=100,      # number of epochs
        imgsz=640,      # image size
        batch=16,       # batch size
        patience=20,    # early stopping patience
        name='waste_sorter_3cat',  # save to runs/detect/waste_sorter_3cat
        cache=True,     # cache images for faster training
        device='0'      # use GPU if available
    )
    
    # Validate the model
    results = model.val()
    
    print("Training completed. Model saved in runs/detect/waste_sorter_3cat")

if __name__ == "__main__":
    main()
