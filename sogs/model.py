from . import db

from base64 import b64encode

import os
import time


def get_rooms():
    """ get a list of rooms with their full info filled out """
    with db.pool as conn:
        result = conn.execute("SELECT * FROM rooms ORDER BY token")
        return [{k: row[k] for k in row.keys()} for row in result]


def get_room(room_token):
    """ Looks up a room by token and returns its info; returns None if the room doesn't exist """
    with db.pool as conn:
        result = conn.execute("SELECT * FROM rooms WHERE token = ?", [room_token])
        row = result.fetchone()
        if row:
            return {k: row[k] for k in row.keys()}
        return None


def get_user(session_id):
    """ get a user by their session id """
    with db.pool as conn:
        result = conn.execute("SELECT * FROM users WHERE session_id = ?", [session_id])
        row = result.fetchone()
        if row:
            return {k: row[k] for k in row.keys()}
        return None


def add_post_to_room(user_id, room_id, data, sig, rate_limit_size=5, rate_limit_interval=16.0):
    """ insert a post into a room from a user given room id and user id
    trims off padding and stores as needed
    """
    with db.pool as conn:
        since_limit = time.time() - rate_limit_interval
        result = conn.execute("SELECT COUNT(*) FROM messages WHERE room = ? AND user = ? AND posted >= ?", [room_id, user_id, since_limit])
        row = result.fetchone()
        if row[0] >= rate_limit_size:
            # rate limit hit
            return

        result = conn.execute("INSERT INTO messages(room, user, data, data_size, signature) VALUES(?, ?, ?, ?, ?) RETURNING *", [user_id, room_id, data.rtrim(b'\x00'), len(data), sig])
        row = result.fetchone()
        msg = {'timestamp': row['posted'], 'server_id': row['id']}
        return msg


def get_room_image_json_blob(room_id):
    """ return a json object with base64'd file contents for the image of a room """
    filename = None
    with db.pool as conn:
        # todo: this query sucks
        result = conn.execute("SELECT filename FROM files WHERE id IN ( SELECT image FROM rooms WHERE token = ? LIMIT 1 ) LIMIT 1", [room_id])
        row = result.fetchone()
        if row:
            filename = row[0]
    if filename and os.path.exists(filename):
        with open(filename, 'rb') as f:
            return {'status_code': 200, "result": b64encode(f.read())}
    else:
        return {"status_code": 404}

def get_mods_for_room(room_id):
    mods = list()
    with db.pool as conn:
        result = conn.execute("SELECT session_id FROM user_permissions WHERE room = ? AND moderator AND visible_mod", [room_id])
        for row in result:
            mods.append(row[0])
    return mods


def get_deletions_deprecated(room_id, since):
    msgs = list()
    with db.pool as conn:
        result = None
        if since:
            result = conn.execute("SELECT id, updated FROM messages WHERE room = ? AND updated > ? AND data IS NULL ORDER BY updated LIMIT 256", [room_id, since])
        else:
            result = conn.execute("SELECT id, updated FROM messages WHERE room = ? AND data IS NULL ORDER BY updated DESC LIMIT 256", [room_id])
        for row in result:
            msgs.append({'id': row[0], 'updated': row[1]})
    return msgs

def get_message_deprecated(room_id, since):
    msgs = list()
    with db.pool as conn:
        result = None
        if since:
            result = conn.execute("SELECT * FROM message_details WHERE room = ? AND id > ? AND data IS NOT NULL ORDER BY id LIMIT 256", [room_id, since])
        else:
            result = conn.execute("SELECT * FROM message_details WHERE room = ? AND data IS NOT NULL ORDER BY id DESC LIMIT 256", [room_id])
        for row in result:
            msgs.append({'server_id': row[0], 'public_key': row[-1], 'timestamp': row[3], 'data': row[6], 'signature': row[8]})
    return msgs


def ensure_user_exists(session_id):
    """
    make sure a user exists in the database
    """
    with db.pool as conn:
        conn.execute("INSERT INTO users(session_id) VALUES(?) ON CONFLICT DO NOTHING", [session_id])
