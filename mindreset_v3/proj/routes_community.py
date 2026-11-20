"""Comunidad anónima: perfil con alias y avatar, foro con búsqueda."""
import re
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import app as core
import chatbot

router = APIRouter()
member = core.require_roles("student", "psychologist", "admin")
CATEGORIES = ["Estrés", "Sueño", "Estudios", "Ánimo", "Consejos", "Otros"]
ALIAS_RE = re.compile(r"^[\w .\-]{3,24}$", re.UNICODE)
AVATAR_RE = re.compile(r"^(p[1-5]|data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]{20,38000})$")
_hits = defaultdict(deque)


def _rate(uid, limit=12, window=3600):
    q = _hits[uid]
    now = time.time()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Estás publicando muy seguido. Tómate un respiro y vuelve en un rato.")
    q.append(now)


def _author(row, prefix=""):
    return {"alias": row[prefix + "alias"] or "Anónimo/a", "avatar": row[prefix + "avatar"] or "p1"}


class ProfileIn(BaseModel):
    alias: str = Field(min_length=3, max_length=24)
    avatar: str = Field(min_length=2, max_length=40000)


@router.get("/api/community/profile")
def get_profile(user=Depends(member)):
    return {"alias": user.get("alias"), "avatar": user.get("avatar") or ("p1" if user.get("alias") else "")} if user.get("alias") else None


@router.put("/api/community/profile")
def set_profile(data: ProfileIn, user=Depends(core.require_roles("student"))):
    alias = " ".join(data.alias.split())
    if not ALIAS_RE.match(alias):
        raise HTTPException(422, "El alias debe tener de 3 a 24 caracteres (letras, números, espacios, punto o guion).")
    if alias.lower() in (user["username"].lower(), user["display_name"].lower()) or user["display_name"].lower() in alias.lower():
        raise HTTPException(422, "Para mantener tu anonimato, el alias no debe parecerse a tu nombre real ni a tu usuario.")
    if not AVATAR_RE.match(data.avatar):
        raise HTTPException(422, "Avatar inválido: elige uno de la lista o sube una imagen JPG, PNG o WebP pequeña.")
    con = core.db()
    try:
        con.execute("UPDATE users SET alias=?, avatar=?, rev=rev+1, synced=0 WHERE id=?", (alias, data.avatar, user["id"]))
        con.commit()
    except Exception:
        con.close()
        raise HTTPException(409, "Ese alias ya está en uso. Prueba con otro.")
    con.close()
    core.SYNC_WAKE.set()
    return {"alias": alias, "avatar": data.avatar}


@router.get("/api/community/posts")
def list_posts(q: str = "", category: str = "", offset: int = 0, user=Depends(member)):
    where, args = ["p.hidden=0"], []
    if q.strip():
        like = "%" + q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(lower(p.title) LIKE ? ESCAPE '\\' OR lower(p.body) LIKE ? ESCAPE '\\')")
        args += [like, like]
    if category in CATEGORIES:
        where.append("p.category=?")
        args.append(category)
    con = core.db()
    rows = con.execute(f"""SELECT p.*, u.alias, u.avatar, (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id AND c.hidden=0) n_comments
                           FROM posts p JOIN users u ON u.id=p.author_id WHERE {' AND '.join(where)}
                           ORDER BY p.id DESC LIMIT 20 OFFSET ?""", args + [max(0, offset)]).fetchall()
    con.close()
    return {"categories": CATEGORIES, "posts": [{"id": r["id"], "category": r["category"], "title": r["title"], "excerpt": r["body"][:180],
                                                   "created_at": r["created_at"], "comments": r["n_comments"], "mine": r["author_id"] == user["id"], **_author(r)} for r in rows]}


class PostIn(BaseModel):
    category: str
    title: str = Field(min_length=3, max_length=100)
    body: str = Field(min_length=5, max_length=2000)


@router.post("/api/community/posts")
def create_post(data: PostIn, user=Depends(core.require_roles("student"))):
    if not user.get("alias"):
        raise HTTPException(400, "Primero crea tu perfil anónimo.")
    if data.category not in CATEGORIES:
        raise HTTPException(422, "Categoría inválida.")
    _rate(user["id"])
    con = core.db()
    cur = con.execute("INSERT INTO posts(author_id,category,title,body,created_at) VALUES(?,?,?,?,?)",
                      (user["id"], data.category, data.title.strip(), data.body.strip(), core.now_iso()))
    con.commit()
    con.close()
    core.SYNC_WAKE.set()
    support = chatbot.is_crisis(data.title + " " + data.body)
    return {"id": cur.lastrowid, "support": support, "resources": chatbot.HELP_RESOURCES if support else None}


@router.get("/api/community/posts/{post_id}")
def get_post(post_id: int, user=Depends(member)):
    con = core.db()
    p = con.execute("SELECT p.*, u.alias, u.avatar FROM posts p JOIN users u ON u.id=p.author_id WHERE p.id=? AND p.hidden=0", (post_id,)).fetchone()
    if not p:
        con.close()
        raise HTTPException(404, "Publicación no encontrada.")
    cs = con.execute("SELECT c.*, u.alias, u.avatar FROM comments c JOIN users u ON u.id=c.author_id WHERE c.post_id=? AND c.hidden=0 ORDER BY c.id", (post_id,)).fetchall()
    con.close()
    return {"id": p["id"], "category": p["category"], "title": p["title"], "body": p["body"], "created_at": p["created_at"], "mine": p["author_id"] == user["id"], **_author(p),
            "comments": [{"id": c["id"], "body": c["body"], "created_at": c["created_at"], "mine": c["author_id"] == user["id"], **_author(c)} for c in cs]}


class CommentIn(BaseModel):
    body: str = Field(min_length=2, max_length=1000)


@router.post("/api/community/posts/{post_id}/comments")
def add_comment(post_id: int, data: CommentIn, user=Depends(core.require_roles("student"))):
    if not user.get("alias"):
        raise HTTPException(400, "Primero crea tu perfil anónimo.")
    _rate(user["id"], limit=30)
    con = core.db()
    if not con.execute("SELECT 1 FROM posts WHERE id=? AND hidden=0", (post_id,)).fetchone():
        con.close()
        raise HTTPException(404, "Publicación no encontrada.")
    cur = con.execute("INSERT INTO comments(post_id,author_id,body,created_at) VALUES(?,?,?,?)", (post_id, user["id"], data.body.strip(), core.now_iso()))
    con.commit()
    con.close()
    core.SYNC_WAKE.set()
    support = chatbot.is_crisis(data.body)
    return {"id": cur.lastrowid, "support": support, "resources": chatbot.HELP_RESOURCES if support else None}


def _can_moderate(user, author_id):
    return user["id"] == author_id or user["role"] in ("psychologist", "admin")


@router.delete("/api/community/posts/{post_id}")
def delete_post(post_id: int, user=Depends(member)):
    con = core.db()
    p = con.execute("SELECT author_id FROM posts WHERE id=?", (post_id,)).fetchone()
    if not p or not _can_moderate(user, p["author_id"]):
        con.close()
        raise HTTPException(404, "Publicación no encontrada.")
    con.execute("UPDATE posts SET hidden=1, rev=rev+1, synced=0 WHERE id=?", (post_id,))
    con.commit()
    con.close()
    core.SYNC_WAKE.set()
    return {"ok": True}


@router.delete("/api/community/comments/{comment_id}")
def delete_comment(comment_id: int, user=Depends(member)):
    con = core.db()
    c = con.execute("SELECT author_id FROM comments WHERE id=?", (comment_id,)).fetchone()
    if not c or not _can_moderate(user, c["author_id"]):
        con.close()
        raise HTTPException(404, "Comentario no encontrado.")
    con.execute("UPDATE comments SET hidden=1, rev=rev+1, synced=0 WHERE id=?", (comment_id,))
    con.commit()
    con.close()
    core.SYNC_WAKE.set()
    return {"ok": True}
