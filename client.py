import grpc
import threading
import time
import chat_pb2
import chat_pb2_grpc

def start_chat(stub, username, room):
    try:
        response = stub.Join(chat_pb2.JoinRequest(username=username, room=room))
        print(f"Chat history for {room}:")
        for message in response.messages:
            print(f"[{message.room}] {message.username}: {message.text} at {message.timestamp}")
    except grpc.RpcError as e:
        print(f"Error joining room: {e.details()}")
        return

    def send_heartbeat():
        while True:
            try:
                stub.Heartbeat(chat_pb2.User(username=username))
            except grpc.RpcError as e:
                print(f"Error sending heartbeat: {e.details()}")
                break
            time.sleep(5)

    threading.Thread(target=send_heartbeat, daemon=True).start()

    while True:
        text = input(">> ")
        if text.strip().lower() == "/leave":
            print(f"{username} left the room.")
            break
        if text.strip():  # Avoid sending empty messages
            msg = chat_pb2.Message(username=username, text=text, room=room)
            try:
                stub.SendMessage(msg)
            except grpc.RpcError as e:
                print(f"Error sending message: {e.details()}")

def run():
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = chat_pb2_grpc.ChatServiceStub(channel)
        username = input("Enter your username: ")
        room = input("Enter the room name: ")
        start_chat(stub, username, room)

if __name__ == "__main__":
    run()
