import os
import shutil
import random
from pathlib import Path
import cv2
import numpy as np

def create_dataset_structure(base_path):
    # Create main directories
    dataset_path = Path(base_path) / 'dataset'
    for split in ['train', 'val']:
        for subdir in ['images', 'labels']:
            (dataset_path / split / subdir).mkdir(parents=True, exist_ok=True)
    return dataset_path

def organize_dataset(source_dir, dataset_path, train_ratio=0.8):
    source_dir = Path(source_dir)
    dataset_path = Path(dataset_path)
    
    # Copy images and labels from train
    print("Copying training data...")
    for file_type in ['images', 'labels']:
        src_dir = source_dir / 'train' / file_type
        dst_dir = dataset_path / 'train' / file_type
        if src_dir.exists():
            print(f"Copying {file_type} from {src_dir} to {dst_dir}")
            for file in src_dir.glob('*.*'):
                shutil.copy2(file, dst_dir / file.name)
                
    # Copy images and labels from valid to val
    print("Copying validation data...")
    for file_type in ['images', 'labels']:
        src_dir = source_dir / 'valid' / file_type
        dst_dir = dataset_path / 'val' / file_type
        if src_dir.exists():
            print(f"Copying {file_type} from {src_dir} to {dst_dir}")
            for file in src_dir.glob('*.*'):
                shutil.copy2(file, dst_dir / file.name)
    
    # Shuffle images
    random.shuffle(all_images)
    
    # Split into train and validation sets
    split_idx = int(len(all_images) * train_ratio)
    train_images = all_images[:split_idx]
    val_images = all_images[split_idx:]
    
    # Process and copy images
    for split_name, image_list in [('train', train_images), ('val', val_images)]:
        for img_path, class_id in image_list:
            # Read image
            img = cv2.imread(str(img_path))
            if img is None:
                print(f"Warning: Could not read image {img_path}")
                continue
            
            # Get image dimensions
            height, width = img.shape[:2]
            
            # Create YOLO format label
            # Simple label: object is considered to occupy the middle 60% of the image
            x_center = 0.5
            y_center = 0.5
            w = 0.6
            h = 0.6
            
            # Copy image
            new_img_path = dataset_path / split_name / 'images' / img_path.name
            shutil.copy2(img_path, new_img_path)
            
            # Create label file
            label_path = dataset_path / split_name / 'labels' / (img_path.stem + '.txt')
            with open(label_path, 'w') as f:
                # YOLO format: class_id x_center y_center width height
                f.write(f"{class_id} {x_center} {y_center} {w} {h}")
            
            print(f"Processed {img_path.name} to {split_name} set")

def main():
    source_dir = 'Waste_Sorter_ToTrain'
    dataset_path = create_dataset_structure(os.getcwd())
    
    print("Starting dataset organization...")
    organize_dataset(source_dir, dataset_path)
    print("Dataset organization completed!")
    
    # Create YAML file
    yaml_content = """path: ../dataset
train: train/images
val: val/images

names:
  0: biodegradable
  1: non_biodegradable
  2: recyclable"""
    
    with open(dataset_path / 'data.yaml', 'w') as f:
        f.write(yaml_content)
    
    print(f"Created dataset structure at {dataset_path}")
    print("You can now run train_model.py to start training")

if __name__ == "__main__":
    main()
