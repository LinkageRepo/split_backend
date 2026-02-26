from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
from django.core.files.base import ContentFile
from .models import Profile
from .serializers import UserSerializer
from django.db.models import Q, Exists, OuterRef
from django.db.models.functions import Coalesce

from .serializers import SearchSerializer, RequestSerializer, FriendSerializer, MessageSerializer
from .models import User, Connection, Message

import json
import base64

class ChatConsumer(WebsocketConsumer):
    def connect(self):
        user = self.scope['user']
        print(user, user.is_authenticated)
        if not user.is_authenticated:
            self.close()
            return

        self.group_name = f"user_{self.scope['user'].id}"
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name) #every time we establish websocket connection we have a unique channel name and we want to add that channel name to a group with group_name
        self.accept()

    def disconnect(self, close_code):
        # Leave room group (only if we joined one — connect() may not have run or may have closed early)
        group_name = getattr(self, "group_name", None)
        if group_name is not None:
            async_to_sync(self.channel_layer.group_discard)(group_name, self.channel_name)

    #------------------------------------------------
    # Receive message from WebSocket
    #------------------------------------------------
    def receive(self, text_data):
        #recieve message from websocket
        data = json.loads(text_data)
        data_source = data.get('source')
        #pretty print python dict
        print('recieve', json.dumps(data, indent=2))

        #Make friend request
        if data_source == 'request.connect':
            self.recieve_request_connect(data)

        #Message list
        elif data_source == 'message.list':
            self.recieve_message_list(data)

        #Message type
        elif data_source == 'message.type':
            self.recieve_message_type(data)

        #message has been sent
        elif data_source == 'message.send':
            self.recieve_message_send(data)

        #get friend list
        elif data_source == 'friend.list':
            self.recieve_friend_list(data) 

        elif data_source == 'request.accept':
            self.recieve_request_accept(data)

        #Search / filter users
        elif data_source == 'search':
            self.recieve_search(data)

        #Get request list
        elif data_source == 'request.list':
            self.recieve_request_list(data)

        #Thumbnail upload
        elif data_source == 'thumbnail':
            self.recieve_thumbnail(data)

    def recieve_message_type(self, data):
        user = self.scope['user']
        recipient_username = data.get('username')

        try:
            recipient = User.objects.get(username=recipient_username)
        except User.DoesNotExist:
            return

        data = {
            'username': user.username
        }
        self.send_group(f"user_{recipient.id}", 'message.type', data)

    def recieve_message_list(self, data):
        user = self.scope['user']
        connection_id = data.get('connectionId')
        page = data.get('page')
        page_size = 5
        try:
            connection = Connection.objects.get(id=connection_id)
        except Connection.DoesNotExist:
            print('Error: couldnt find connection')
            return
        #get messages
        messages = Message.objects.filter(connection=connection).order_by('-created')[page * page_size:(page + 1) * page_size]
        #serialized messages
        serialized_message = MessageSerializer(
            messages,
            context={
                'user': user    
            },
            many=True
        )
        #Get recipient friend
        recipient = connection.sender
        if connection.sender == user:
            recipient = connection.reciever

        #serialize friend
        serialized_friend = UserSerializer(recipient)

        #count the total number of messages for this connection
        messages_count = Message.objects.filter(
            connection=connection
        ).count()

        next_page =page + 1 if messages_count > (page + 1) * page_size else None

        data = {
            'messages': serialized_message.data,
            'next': next_page,
            'friend': serialized_friend.data
        }
        #send back to the requestor
        self.send_group(self.group_name, 'message.list', data)

    def recieve_message_send(self, data):
        user = self.scope['user']
        connection_id = data.get('connectionId')
        message_text = data.get('message')

        try:
            connection = Connection.objects.get(id=connection_id)
        except Connection.DoesNotExist:
            print('Error: couldnt find connection')
            return

        message = Message.objects.create(
            connection=connection,
            user=user,
            text=message_text
        )

        #Get recipient friend
        recipient = connection.sender
        if connection.sender == user:
            recipient = connection.reciever

        #send new message back to sender
        serialized_message = MessageSerializer(message, context={'user': user})
        serialized_friend = UserSerializer(recipient)
        data = {
            'message': serialized_message.data,
            'friend': serialized_friend.data
        }
        self.send_group(self.group_name, 'message.send', data)


        #send new message back to reciever
        serialized_message = MessageSerializer(message, context={'user': recipient})
        serialized_friend = UserSerializer(user)
        data = {
            'message': serialized_message.data,
            'friend': serialized_friend.data
        }
        self.send_group(f"user_{recipient.id}", 'message.send', data)

    def recieve_friend_list(self, data):
        user = self.scope['user']
        #latest message subquery
        latest_message = Message.objects.filter(
            connection=OuterRef('id')
        ).order_by('-created')[:1]
        #Get connections for user
        connection = Connection.objects.filter(
            Q(sender=user) | Q(reciever=user),
            accepted=True
        ).annotate(
            latest_text = latest_message.values('text'),
            latest_created = latest_message.values('created'),
        ).order_by(
            Coalesce('latest_created', 'updated').desc()
        )
        serialized = FriendSerializer(connection, context={'user': user},  many=True)
        #send data back to requesting user
        self.send_group(self.group_name, 'friend.list', serialized.data)

    def recieve_request_accept(self, data):
        username = data.get('username')
        try:
            connection = Connection.objects.get(
                sender__username=username,
                reciever = self.scope['user']
            )
        except Connection.DoesNotExist:
            print('Error connection does not exist')
            return
            #update the connection
        connection.accepted = True
        connection.save()

        serialized = RequestSerializer(connection)
        #send accepted request to sender
        self.send_group(f"user_{connection.sender.id}", 'request.accept', serialized.data)
        #send accepted request to reciever
        self.send_group(f"user_{connection.reciever.id}", 'request.accept', serialized.data)
        
        #send new friend object to sender
        serialized_friend = FriendSerializer(
            connection, 
            context={'user': connection.sender}
        )
        self.send_group(f"user_{connection.sender.id}", 'friend.new', serialized_friend.data) 

        #send new friend object to reciever
        serialized_friend = FriendSerializer( 
            connection, 
            context={'user': connection.reciever}
        )
        self.send_group(f"user_{connection.reciever.id}", 'friend.new', serialized_friend.data) 


    def recieve_request_list(self, data):
        user = self.scope['user']
        connections = Connection.objects.filter(
            reciever=user,
            accepted=False
        )
        serialized = RequestSerializer(connections, many=True)
        self.send_group(self.group_name, 'request.list', serialized.data) 

    def recieve_request_connect(self, data):
        username = data.get('username')
        #attempt to fetch the recieving user
        try:
            reciever = User.objects.get(username=username)
        except User.DoesNotExist:
            print('Error user not found')
            return
        #create connection
        connection, _ = Connection.objects.get_or_create(
            sender=self.scope['user'],
            reciever=reciever
        )
        #serialize the connection
        serialized = RequestSerializer(connection)
        #send back to sender
        self.send_group(f"user_{connection.sender.id}", 'request.connect', serialized.data)
        #send to reciever
        self.send_group(f"user_{connection.reciever.id}", 'request.connect', serialized.data)
        

    def recieve_search(self, data):
        query = data.get('query')
        #get users from query seach term
        users = User.objects.filter(
            Q(username__icontains=query) |
            Q(full_name__icontains=query) | 
            Q(phone_number__icontains=query)
            ).exclude(
                id=self.scope['user'].id
            ).annotate(
                pending_them = Exists(
                    Connection.objects.filter(
                        sender=self.scope['user'],
                        reciever=OuterRef('id'),
                        accepted=False
                    )
                ),
                pending_me = Exists(
                    Connection.objects.filter(
                        sender=OuterRef('id'),
                        reciever=self.scope['user'],
                        accepted=False
                    )
                ),
                connected = Exists(
                    Connection.objects.filter(
                        Q(sender=self.scope['user'], reciever=OuterRef('id')) |
                        Q(sender=OuterRef('id'), reciever=self.scope['user']),
                        accepted=True
                    )
                )
            )

        #serilize results
        serialized = SearchSerializer(users, many=True)
        #send search reults back to this user
        self.send_group(self.group_name, 'search', serialized.data)

    
    def recieve_thumbnail(self, data):
        user = self.scope['user']
        #convert base64 data to django content file
        image_str = data.get('base64')
        image = ContentFile(base64.b64decode(image_str))
        filename = data.get('filename')
        profile, _ = Profile.objects.get_or_create(user=user)

        # Delete the old thumbnail file before saving the new one
        if profile.thumbnail:
            profile.thumbnail.delete(save=False)

        profile.thumbnail.save(filename, image, save=True)

        # Re-fetch user from DB so the serializer picks up the fresh profile
        from .models import User as UserModel
        user = UserModel.objects.get(id=user.id)

        #serialize user
        serialized = UserSerializer(user)
        #send updated user data
        self.send_group(self.group_name, 'thumbnail', serialized.data)

    def send_group(self, group, source, data):
        response = {
            'type': 'broadcast_group',
            'source': source,
            'data': data
        }
        async_to_sync(self.channel_layer.group_send)(group, response)

    def broadcast_group(self, data):
        '''
        data:
            -type: broadcast_group
            -source: source of the data
            -data: whatever ypu want to send as dict
        '''
        data.pop('type')
        self.send(text_data=json.dumps(data))