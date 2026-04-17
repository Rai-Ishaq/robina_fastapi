from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
import cloudinary
import cloudinary.uploader
from app.database import get_db
from app.models.social import Post, PostLike, Comment, CommentLike
from app.models.user import User
from app.models.profile import Profile
from app.utils.helpers import get_current_user, get_verified_user
import uuid

router = APIRouter(prefix="/social", tags=["social"])


def _post_dict(post, current_user_id, db):
    user = db.query(User).filter(User.id == post.user_id).first()
    profile = db.query(Profile).filter(Profile.user_id == post.user_id).first()
    is_liked = db.query(PostLike).filter(
        PostLike.post_id == post.id,
        PostLike.user_id == current_user_id
    ).first() is not None

    preview = db.query(Comment).filter(
        Comment.post_id == post.id,
        Comment.parent_id == None
    ).order_by(desc(Comment.created_at)).limit(2).all()

    return {
        "id": str(post.id),
        "user_id": str(post.user_id),
        "user_name": user.full_name if user else "Unknown",
        "user_city": profile.city if profile else "",
        "user_photo": profile.profile_photo if profile else None,
        "user_code": user.user_code if user else "",
        "verification_status": user.verification_status if user else "none",
        "is_premium": user.is_premium if user else False,
        "text": post.text,
        "media_url": post.media_url,
        "media_type": post.media_type,
        "like_count": post.like_count,
        "comment_count": post.comment_count,
        "is_liked": is_liked,
        "is_mine": str(post.user_id) == str(current_user_id),
        "created_at": post.created_at.isoformat(),
        "preview_comments": [_comment_dict(c, current_user_id, db) for c in preview],
    }


def _comment_dict(comment, current_user_id, db, include_replies=True):
    user = db.query(User).filter(User.id == comment.user_id).first()
    profile = db.query(Profile).filter(Profile.user_id == comment.user_id).first()
    is_liked = db.query(CommentLike).filter(
        CommentLike.comment_id == comment.id,
        CommentLike.user_id == current_user_id
    ).first() is not None

    replies = []
    if include_replies:
        raw_replies = db.query(Comment).filter(
            Comment.parent_id == comment.id
        ).order_by(Comment.created_at).all()
        replies = [_comment_dict(r, current_user_id, db, include_replies=False) for r in raw_replies]

    return {
        "id": str(comment.id),
        "user_id": str(comment.user_id),
        "user_name": user.full_name if user else "Unknown",
        "user_photo": profile.profile_photo if profile else None,
        "text": comment.text,
        "like_count": comment.like_count,
        "is_liked": is_liked,
        "is_mine": str(comment.user_id) == str(current_user_id),
        "parent_id": str(comment.parent_id) if comment.parent_id else None,
        "replies": replies,
        "created_at": comment.created_at.isoformat(),
        "verification_status": user.verification_status if user else "none",
    }


# ── FEED ──────────────────────────────────────────────────────────────────────

@router.get("/feed")
def get_feed(
    page: int = 1,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit
    posts = db.query(Post).order_by(desc(Post.created_at)).offset(offset).limit(limit).all()
    return [_post_dict(p, current_user.id, db) for p in posts]


# ── CREATE POST ───────────────────────────────────────────────────────────────

@router.post("/posts")
async def create_post(
    text: Optional[str] = Form(None),
    media_type: str = Form("text"),
    file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not text and not file:
        raise HTTPException(400, "Post must have text or media")

    media_url = None
    if file:
        try:
            contents = await file.read()
            resource_type = "video" if media_type == "video" else "image"
            result = cloudinary.uploader.upload(
                contents,
                folder="robina_social",
                resource_type=resource_type
            )
            media_url = result.get("secure_url")
        except Exception as e:
            raise HTTPException(500, f"Upload failed: {str(e)}")

    post = Post(
        user_id=current_user.id,
        text=text,
        media_url=media_url,
        media_type=media_type,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return _post_dict(post, current_user.id, db)


# ── DELETE POST ───────────────────────────────────────────────────────────────

@router.delete("/posts/{post_id}")
def delete_post(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")
    if str(post.user_id) != str(current_user.id):
        raise HTTPException(403, "Not your post")
    db.delete(post)
    db.commit()
    return {"success": True}


# ── LIKE POST ─────────────────────────────────────────────────────────────────

@router.post("/posts/{post_id}/like")
def toggle_like(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")

    existing = db.query(PostLike).filter(
        PostLike.post_id == post_id,
        PostLike.user_id == current_user.id
    ).first()

    if existing:
        db.delete(existing)
        post.like_count = max(0, post.like_count - 1)
        liked = False
    else:
        db.add(PostLike(post_id=post.id, user_id=current_user.id))
        post.like_count += 1
        liked = True

    db.commit()
    return {"liked": liked, "like_count": post.like_count}


# ── COMMENTS ──────────────────────────────────────────────────────────────────

@router.get("/posts/{post_id}/comments")
def get_comments(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    comments = db.query(Comment).filter(
        Comment.post_id == post_id,
        Comment.parent_id == None
    ).order_by(Comment.created_at).all()
    return [_comment_dict(c, current_user.id, db) for c in comments]


@router.post("/posts/{post_id}/comments")
def add_comment(
    post_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")

    text = body.get("text", "").strip()
    parent_id = body.get("parent_id")
    if not text:
        raise HTTPException(400, "Comment text required")

    comment = Comment(
        post_id=post.id,
        user_id=current_user.id,
        text=text,
        parent_id=uuid.UUID(parent_id) if parent_id else None
    )
    db.add(comment)
    post.comment_count += 1
    db.commit()
    db.refresh(comment)
    return _comment_dict(comment, current_user.id, db)


# ── LIKE COMMENT ──────────────────────────────────────────────────────────────

@router.post("/comments/{comment_id}/like")
def toggle_comment_like(
    comment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(404, "Comment not found")

    existing = db.query(CommentLike).filter(
        CommentLike.comment_id == comment_id,
        CommentLike.user_id == current_user.id
    ).first()

    if existing:
        db.delete(existing)
        comment.like_count = max(0, comment.like_count - 1)
        liked = False
    else:
        db.add(CommentLike(comment_id=comment.id, user_id=current_user.id))
        comment.like_count += 1
        liked = True

    db.commit()
    return {"liked": liked, "like_count": comment.like_count}


# ── SOCIAL PROFILE ────────────────────────────────────────────────────────────

@router.get("/profile/{user_id}")
def get_social_profile(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    posts = db.query(Post).filter(
        Post.user_id == user_id
    ).order_by(desc(Post.created_at)).all()

    total_likes = sum(p.like_count for p in posts)
    total_comments = sum(p.comment_count for p in posts)

    return {
        "user_id": str(user.id),
        "user_name": user.full_name,
        "user_code": user.user_code or "",
        "city": profile.city if profile else "",
        "photo": profile.profile_photo if profile else None,
        "posts_count": len(posts),
        "total_likes": total_likes,
        "total_comments": total_comments,
        "posts": [_post_dict(p, current_user.id, db) for p in posts],
    }
