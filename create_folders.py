import os

path = "data/Philippines"

for file in os.listdir(path):
    if file.endswith(".jpg") or file.endswith(".jpeg") or file.endswith(".png"):
        os.makedirs(os.path.join(path, file.split(".")[0]), exist_ok=True)
        os.rename(os.path.join(path, file), os.path.join(path, file.split(".")[0], file))
        print(f"Moved {file} to {os.path.join(path, file.split(".")[0])}")