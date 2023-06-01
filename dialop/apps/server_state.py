import threading
from s3_json_bucket import S3JsonBucket
from time import strftime, gmtime
import uuid

S3_BUCKET_NAME = "collaborative-dialogue-ms"

class Room:

    def __init__(self, room_id, num_players=2):
        self.id = room_id
        self.num_players = num_players
        self.players = []
        self.players_mturk_info = []
        # To prevent room fm being closed in final round when 1st player quits
        self.waiting_to_close = False
        self.all_games = []
        self.game = None
        self.game_started = False
        self.logged = False

    def new_game(self, game):
        self.all_games.append(game)
        self.game = game
        self.game_started = True
        print("Game started!")

    def is_free(self):
        return len(self.players) < self.num_players

    def is_ready(self):
        return len(self.players) == self.num_players

    def add_player(self, player_client_id, player_mturk_info):
        self.players.append(player_client_id)
        self.players_mturk_info.append(player_mturk_info)

    def drop_player(self, player_idx):
        print("Number of players in room %s: %s" % (self.id, len(self.players)))
        print("Dropping player %s from room %s" % (player_idx, self.id))
        self.players.pop(player_idx)
        self.players_mturk_info.pop(player_idx)
        print("Number of players in room %s: %s" % (self.id, len(self.players)))


class ServerState:

    def __init__(self, app, num_players=2):
        self.app = app
        self.lock = threading.RLock()
        self.num_players = num_players

        self.rooms = {}
        self.room_assignments = {}

    def connect_client(self, client_id, mturk_info):
        """Add client to the next available room.

        Returns:
            room_id: id of the room this client has been assigned to
            ready: whether the room has two players now
        """
        with self.lock:
            self.app.logger.debug("connecting to room")
            free_room_ids = [room_id for room_id in self.rooms.keys() if self.rooms[room_id].is_free()]
            if len(free_room_ids) == 0:
                room_id = uuid.uuid4().hex
                self.rooms[room_id] = Room(room_id, self.num_players)
                self.rooms[room_id].add_player(client_id, mturk_info)
                self.room_assignments[client_id] = room_id
                ready = False
            else:
                room_id = free_room_ids[0]
                self.rooms[room_id].add_player(client_id, mturk_info)
                self.room_assignments[client_id] = room_id
                ready = self.rooms[room_id].is_ready()

            if ready:
                self.app.logger.debug("%s ready with players %s", room_id, self.rooms[room_id].players)

            return room_id, ready

    def initialize_room(self, room_id, game):
        with self.lock:
            self.rooms[room_id].new_game(game)

    def get_room_for_client(self, client_id):
        with self.lock:
            return self.rooms[self.room_assignments[client_id]]

    def get_mturk_info(self, client_id):
        with self.lock:
            room = self.rooms[self.room_assignments[client_id]]
            player_idx = room.players.index(client_id)
            return room.players_mturk_info[player_idx]

    def prepare_room_to_close(self, room_id):
        with self.lock:
            room = self.rooms[room_id]
            if room.waiting_to_close:
                # Other player to quit, we can close when this player disconnects
                room.waiting_to_close = False
                # All done now, save game
                self.save(room_id)
            else:
                # Wait for the other player to disconnect
                room.waiting_to_close = True

    def save(self, room_id):
        with self.lock:
            self.app.logger.debug("Saving game in room %s", room_id)
            room = self.rooms[room_id]
            if not room.logged:
                timestamp = strftime("%Y-%m-%d_%H-%M-%S", gmtime())
                token = uuid.uuid4().hex
                path = timestamp + "_" + token + ".json"
                jsbucket = S3JsonBucket(S3_BUCKET_NAME)
                jsbucket.dump(path, {
                    "mturk_info": room.players_mturk_info,
                    "games": [game.get_game_info() for game in room.all_games]
                    })
                room.logged = True

    def close(self, room_id):
        with self.lock:
            if room_id in self.rooms:
                players = self.rooms[room_id].players
                for p in players:
                    del self.room_assignments[p]
                del self.rooms[room_id]
                self.app.logger.debug("Closed room %s", room_id)
            else:
                self.app.logger.debug("Room %s already closed", room_id)
