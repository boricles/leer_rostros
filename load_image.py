import os
import uuid
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

from deepface import DeepFace
import chromadb

os.makedirs("database", exist_ok=True)


class LoadImage():
    def __init__(self,img_path: str, hospital_name: str, name = "unknown", ci = "unknown"):
        self.img_path = img_path
        self.name = name
        self.ci = ci
        self.hospital_name = hospital_name

    def loadData(self):
        chromadbClient = chromadb.PersistentClient(
            path="database/persistent_client_database"
        )

        collection = chromadbClient.get_or_create_collection(
            name="rostros_usuarios",
            metadata={"hnsw:space": "cosine"} 
        )

        print("Analizando imagen y extrayendo características...")
        resultado = DeepFace.represent(
            img_path=self.img_path, 
            model_name="Facenet",
            enforce_detection=False
        )

        vector_rostro = resultado[0]["embedding"]
        # print("vector_rostro",vector_rostro)

        new_id = f"usr_{uuid.uuid4()}"

        collection.add(
            embeddings=[vector_rostro],
            metadatas=[{"nombre": self.name, "rol": self.hospital_name}],
            ids=[new_id]
        )

        print("¡Datos guardados localmente en la carpeta 'database/' con éxito!")
    
