import copy
import json
import logging
import os
import random
import string
from collections import Counter

import flask
import flask_socketio as io
from dialop.games import MediationGame, OptimizationGame, PlanningGame
from flask import request, send_from_directory, session, url_for

from server_state import ServerState

flask.logging.default_handler.setFormatter(logging.Formatter("[%(filename)s:%(lineno)s:%(funcName)s] -- %(message)s"))

clients = []
num_games_per_client = Counter()
NUM_PRACTICE_ROUNDS = os.environ.get("num_practice_rounds", 1)
NUM_ROUNDS = os.environ.get("num_rounds", 1)
NUM_GAMES = os.environ.get("num_games", 1)
MAX_GAMES = os.environ.get("max_games", 1)
# Humans can send messages anytime by default
TAKE_TURNS = os.environ.get("take_turns", False)
GAME = os.environ.get("game")

assert GAME in ("optimization", "planning", "mediation"), \
    "Specify a game: `game={optimization, planning, mediation} flask run`."
rootdir = GAME

if GAME == "optimization":
    GAME_CLS = OptimizationGame
    rootdir = "optimization"
    NUM_PLAYERS = 2
elif GAME == "planning":
    GAME_CLS = PlanningGame
    NUM_PLAYERS = 2
elif GAME == "mediation":
    GAME_CLS = MediationGame
    NUM_PLAYERS = 3

app = flask.Flask(
    __name__,
    static_url_path=f"/static",
    static_folder=f"{rootdir}/static",
    template_folder=f"{rootdir}/templates",
  )
app.config["SECRET_KEY"] = os.urandom(12).hex()
socketio = io.SocketIO(app, cors_allowed_origins="*", manage_session=False)
state = ServerState(app, num_players=NUM_PLAYERS)
LOG = flask.logging.create_logger(app)
LOG.setLevel(logging.DEBUG)

@app.route("/")
def index():
    return flask.render_template("index.html")

@app.route("/game")
def game():
    return flask.render_template("game.html")

@app.route("/qual")
def qual():
    return flask.render_template("qual.html")

@app.get('/media/<path:path>')
def send_media(path):
    return send_from_directory(
        directory=app.static_folder, path=path
    )

def generate_random_string(length):
    letters = string.ascii_letters
    return ''.join(random.choice(letters) for _ in range(length))

@socketio.on("connect")
def connect():
    mturk_info = mturk_params(request.args)
    if mturk_info is None:
        mturk_info = {}
    LOG.info("%s connected | mturk %s", request.sid, mturk_info)
    assert request.sid not in clients, f"Client {request.sid} already connected?"
    io.emit("setup", {
        "sound": url_for('static', filename='ping.mp3'),
        },
            to=request.sid)

    LOG.debug("Getting session cookie")
    user_id = session.get('user_id')
    if user_id is None:
        LOG.debug("No session cookie found")
        user_id = generate_random_string(10)
        session['user_id'] = user_id
        LOG.debug("Session cookie generated")
    else:
        LOG.debug("Session cookie found")
    mturk_info["user_cookie"] = user_id

    # Check if worker has already played too many games
    if num_games_per_client[mturk_info["workerId"]] >= MAX_GAMES:
        # Get client ID and send message to client
        io.emit("max_games", to=request.sid)
        return
    clients.append(request.sid)

    # Add client to next available room
    room_id, ready = state.connect_client(request.sid, mturk_info)
    io.join_room(room_id)
    LOG.debug("%s connected to room %s", request.sid, room_id)
    if ready:
        start_new_game(room_id)

@socketio.on("disconnect")
def disconnect():
    LOG.info("%s disconnected", request.sid)
    # room already closed by the other user
    if request.sid not in state.room_assignments:
        return

    room_id = state.room_assignments[request.sid]
    if room_id not in state.rooms:
        return
    room = state.rooms[room_id]

    if not room.game_started:
        # if disconnecting before game starts
        player_idx = room.players.index(request.sid)
        room.drop_player(player_idx)
        return

    # if disconnecting prematurely after another player is in the room
    if len(room.all_games) < NUM_GAMES and len(room.players) > 1:
        player_idx = room.players.index(request.sid)
        LOG.info("Bad user %s disconnected early, mturk_info %s",
                 request.sid,
                 room.players_mturk_info[player_idx])
        state.save(room.id)

    if not room.waiting_to_close:
        state.close(room_id)
        io.emit("disconnected", to=room_id)
        io.close_room(room_id)

@socketio.on("action")
def action(ac_data):
    room = state.get_room_for_client(request.sid)
    LOG.debug("Received action %s in room %s ", ac_data, room.id)
    game = room.game
    metadata = {"mturk_id": mturk_params(request.args)["workerId"]}
    if "virtual_room_id" in ac_data:
        vroom = ac_data["virtual_room_id"]
        old_player = copy.deepcopy(game.turn_players[vroom])
        game.message(ac_data, vroom=vroom, metadata=metadata)
        for i in game.virtual_rooms[vroom]:
            io.emit("action", {"data": ac_data}, to=room.players[i])
        if TAKE_TURNS:
            io.emit("your_turn", {"vroom": vroom}, to=room.players[game.turn_players[vroom]])
            io.emit("end_turn", {"vroom": vroom}, to=room.players[old_player])
    else:
        game.message(ac_data, metadata)
        for i, client_id in enumerate(room.players):
            io.emit("action", {"data": ac_data}, to=client_id)
        # Let current turn player know
        if TAKE_TURNS:
            io.emit("your_turn", to=room.players[game.turn_player])
            io.emit("end_turn", {"vroom": vroom}, to=room.players[1 - game.turn_players[vroom]])

@socketio.on("proposal")
def proposal(proposal_data):
    room = state.get_room_for_client(request.sid)
    LOG.debug("Proposal %s in room %s ", proposal_data, room.id)
    game = room.game
    proposal = json.loads(proposal_data["data"])
    proposing_player = proposal_data["from_player"]
    metadata = {"mturk_id": mturk_params(request.args)["workerId"]}
    if NUM_PLAYERS == 2:
        recv_obs = game.propose(proposal, proposing_player, metadata=metadata)
        # Send text version of proposal for display in chat window
        proposal = {
            "data": game.proposal_readable,
            "from_player": proposal_data["from_player"],
        }
        for i, client_id in enumerate(room.players):
            io.emit("action", {"data": proposal}, to=client_id)
        # Send proposal and info to the receiving player
        io.emit("proposal_available", recv_obs, to=room.players[1 - proposing_player])
        if TAKE_TURNS:
            io.emit("your_turn", to=room.players[game.turn_player])
        LOG.debug("Proposal made, is_full_proposal=%s", game.is_full_proposal)
        LOG.debug("Proposal info for recv player=%s", recv_obs)

    # In multiagent case, agent is allowed to make proposal any time
    else:
        recv_obss = game.propose(proposal, proposing_player, metadata)
        for vroom_idx, vroom_players in enumerate(game.virtual_rooms):
            # Send text version of proposal for display in chat window
            proposal = {
                "data": recv_obss[vroom_idx]["proposal_readable"],
                "type": "utterance",
                "from_player": proposal_data["from_player"],
                "virtual_room_id": vroom_idx,
            }
            for i in vroom_players:
                io.emit("action", {"data": proposal}, to=room.players[i])
            human_client_id = room.players[game.turn_players[vroom_idx]]
            io.emit("proposal_available", recv_obss[vroom_idx],
                    to=human_client_id)
            if TAKE_TURNS:
                io.emit("your_turn", {"vroom": vroom_idx}, to=human_client_id)

@socketio.on("proposal_response")
def proposal_response(data):
    room = state.get_room_for_client(request.sid)
    LOG.debug("Proposal response %s in room %s ", data, room.id)
    game = room.game
    from_player = data["from_player"]
    metadata = {"mturk_id": mturk_params(request.args)["workerId"]}
    game_over, player_infos = game.proposal_response(data, from_player, metadata)
    message = {**data, "data": "Proposal accepted" if data["accept"] else
               "Proposal rejected"}

    if NUM_PLAYERS == 2:
        for i, client_id in enumerate(room.players):
            io.emit("action", {"data": message}, to=client_id)
    else:
        for player in game.virtual_rooms[data["from_player"]]:
            io.emit("action", {"data": message}, to=room.players[player])

    if not game_over:
        return

    players_mturk_info = room.players_mturk_info
    for player in players_mturk_info:
        mturk_info = player
        if mturk_info["workerId"]:
            num_games_per_client[mturk_info["workerId"]] += 1
    info = game.get_game_info()
    LOG.debug(info.keys())
    for i, info in enumerate(player_infos):
        LOG.debug("Proposal outcome %d: %s", i, info)
    if len(room.all_games) < NUM_GAMES:
        for i, player in enumerate(room.players):
            io.emit("end_game", player_infos[i], to=player)
    else:
        # LOG.debug("Finished, ending in room %s", room.id)
        io.emit("end", {"players": room.players}, to=room.id)
    state.save(room.id)

def start_new_game(room_id):
    mturk_info = mturk_params(request.args)
    room = state.rooms[room_id]
    game = GAME_CLS({"take_turns": TAKE_TURNS})
    obss = game.reset()
    state.initialize_room(room_id, game)
    LOG.debug("Beginning game in room %s", room_id)

    # Show instructions
    for i, client_id in enumerate(room.players):
        obss[i].update({
            "player_id": i,
            "worker_id": mturk_info["workerId"],
        })
        LOG.debug("Obs for player %s: %s", i, obss[i])
        io.emit("begin", obss[i], to=client_id)

    turn_players = room.game.turn_players if TAKE_TURNS else room.players
    for vroom, player in enumerate(turn_players):
        print("PLAYER: ", player)
        io.emit("your_turn", {"vroom": vroom}, to=player)

def mturk_params(req_params):
    keys = ("assignmentId", "hitId", "turkSubmitTo", "workerId")
    return {k: req_params.get(k) for k in keys}
