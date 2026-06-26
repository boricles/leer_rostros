import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

from deepface import DeepFace
import chromadb

class SearchImage():
    def __init__(self, img_path: str):
        self.img_path = img_path

    def searchImage(self):
        chromadbClient = chromadb.PersistentClient(
            path="database/persistent_client_database"
        )

        collection = chromadbClient.get_collection(name="rostros_usuarios")

        print("Analizando nueva imagen...")
        resultado = DeepFace.represent(
            img_path= self.img_path, 
            model_name="Facenet",
            enforce_detection=False
        )
        nuevo_vector = resultado[0]["embedding"]
        print("nuevo_vector",nuevo_vector)

        print("Buscando coincidencias en la base de datos vectorial...")
        busqueda = collection.query(
            query_embeddings=[nuevo_vector],
            n_results=10  # Traer solo el resultado más parecido
        )

        print(busqueda['distances'])
        distancia = busqueda['distances'][0][0]
        for i in range(len(busqueda['distances'][0])):
            distancia = busqueda['distances'][0][i]

            if distancia < 1:
                nombre = busqueda['metadatas'][0][i]['nombre']
                rol = busqueda['metadatas'][0][i]['rol']
                id_usuario = busqueda['ids'][0][i]
                print(f"\n✅ ¡Persona Identificada!")
                print(f"👤 Nombre: {nombre}")
                print(f"🪪 ID: {id_usuario}")
                print(f"⚙️ Rol: {rol}")
                print(f"📊 Distancia matemática: {distancia:.4f} (Alta certeza)")
            else:
                print("\n❌ Usuario no reconocido o el rostro no coincide con ningún registro.")
