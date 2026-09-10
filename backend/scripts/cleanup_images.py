from app.api.routes import image_storage

if __name__ == "__main__":
    print(f"removed {image_storage.cleanup_expired()} expired images")
