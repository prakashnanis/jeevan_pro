import grpc
from concurrent import futures
import chat_pb2
import chat_pb2_grpc
from datetime import datetime

class ChatService(chat_pb2_grpc.ChatServiceServicer):
    def __init__(self):
        self.rooms = {}  # Active rooms with users and messages
        self.create_default_rooms()

    def create_default_rooms(self):
        # Initialize some default rooms if needed
        self.rooms["general"] = []  # Example room
        self.rooms["sports"] = []

    def get_chat_history(self, room):
        # Retrieve chat history from the in-memory rooms (messages)
        if room in self.rooms:
            return [chat_pb2.Message(username=msg['username'], text=msg['text'], room=room, timestamp=msg['timestamp'])
                    for msg in self.rooms[room]]
        return []

    def Join(self, request, context):
        room = request.room
        username = request.username
        print(f"Join request: username={username}, room={room}")

        if room not in self.rooms:
            self.rooms[room] = []  # Create the room if it doesn't exist

        # Send the chat history to the user joining the room
        return chat_pb2.StreamMessage(messages=self.get_chat_history(room))

    def SendMessage(self, request, context):
        # Save the message in memory (instead of a database)
        message = {
            'username': request.username,
            'text': request.text,
            'room': request.room,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        if request.room in self.rooms:
            self.rooms[request.room].append(message)
        else:
            self.rooms[request.room] = [message]

        print(f"[{request.room}] {request.username}: {request.text}")
        return chat_pb2.Empty()

    def Heartbeat(self, request, context):
        print(f"Heartbeat received from {request.username}")
        return chat_pb2.Empty()

def serve():
    # Start the gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    chat_pb2_grpc.add_ChatServiceServicer_to_server(ChatService(), server)
    server.add_insecure_port('[::]:50051')
    print("Server started on port 50051")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
