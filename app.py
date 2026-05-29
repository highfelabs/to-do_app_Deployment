import os
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

# ── Database config ────────────────────────────────────────────────────────────
# Swap DATABASE_URL env var for RDS in production:
#   postgresql://user:pass@your-rds-endpoint:5432/todos
os.makedirs("/app/data", exist_ok=True)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:////app/data/todos.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ── Models ─────────────────────────────────────────────────────────────────────

task_tags = db.Table(
    "task_tags",
    db.Column("task_id", db.Integer, db.ForeignKey("task.id"), primary_key=True),
    db.Column("tag_id",  db.Integer, db.ForeignKey("tag.id"),  primary_key=True),
)


class Tag(db.Model):
    id    = db.Column(db.Integer, primary_key=True)
    name  = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(7), default="#6c757d")


class Task(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    text       = db.Column(db.String(300), nullable=False)
    done       = db.Column(db.Boolean, default=False)
    priority   = db.Column(db.String(10), default="medium")   # low / medium / high
    due_date   = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tags       = db.relationship("Tag", secondary=task_tags, backref="tasks")

    @property
    def is_overdue(self):
        return self.due_date and not self.done and self.due_date < date.today()

    @property
    def priority_order(self):
        return {"high": 0, "medium": 1, "low": 2}.get(self.priority, 1)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    filter_by = request.args.get("filter", "all")
    search    = request.args.get("q", "").strip()
    sort_by   = request.args.get("sort", "created")
    tag_filter = request.args.get("tag", "")

    query = Task.query

    if filter_by == "active":
        query = query.filter_by(done=False)
    elif filter_by == "done":
        query = query.filter_by(done=True)

    if search:
        query = query.filter(Task.text.ilike(f"%{search}%"))

    if tag_filter:
        query = query.join(task_tags).join(Tag).filter(Tag.name == tag_filter)

    tasks = query.all()

    # Sort
    if sort_by == "priority":
        tasks.sort(key=lambda t: t.priority_order)
    elif sort_by == "due_date":
        tasks.sort(key=lambda t: (t.due_date is None, t.due_date))
    elif sort_by == "alpha":
        tasks.sort(key=lambda t: t.text.lower())
    else:
        tasks.sort(key=lambda t: t.created_at, reverse=True)

    all_tags     = Tag.query.order_by(Tag.name).all()
    active_count = Task.query.filter_by(done=False).count()
    overdue_count = sum(1 for t in Task.query.filter_by(done=False).all() if t.is_overdue)

    return render_template("index.html",
        tasks=tasks, filter=filter_by, search=search, sort=sort_by,
        all_tags=all_tags, tag_filter=tag_filter,
        active_count=active_count, overdue_count=overdue_count,
        today=date.today().isoformat()
    )


@app.route("/add", methods=["POST"])
def add():
    text     = request.form.get("task", "").strip()
    priority = request.form.get("priority", "medium")
    due_str  = request.form.get("due_date", "").strip()
    tag_ids  = request.form.getlist("tags")
    new_tag  = request.form.get("new_tag", "").strip()

    if not text:
        flash("Task text cannot be empty.", "error")
        return redirect(url_for("index"))

    due = datetime.strptime(due_str, "%Y-%m-%d").date() if due_str else None

    task = Task(text=text, priority=priority, due_date=due)

    # Attach existing tags
    for tid in tag_ids:
        tag = Tag.query.get(int(tid))
        if tag:
            task.tags.append(tag)

    # Create & attach new tag
    if new_tag:
        existing = Tag.query.filter_by(name=new_tag).first()
        if not existing:
            existing = Tag(name=new_tag, color=_random_color(new_tag))
            db.session.add(existing)
        task.tags.append(existing)

    db.session.add(task)
    db.session.commit()
    flash("Task added!", "success")
    return redirect(url_for("index"))


@app.route("/toggle/<int:task_id>")
def toggle(task_id):
    task = Task.query.get_or_404(task_id)
    task.done = not task.done
    db.session.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/delete/<int:task_id>")
def delete(task_id):
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    flash("Task deleted.", "info")
    return redirect(request.referrer or url_for("index"))


@app.route("/edit/<int:task_id>", methods=["GET", "POST"])
def edit(task_id):
    task     = Task.query.get_or_404(task_id)
    all_tags = Tag.query.order_by(Tag.name).all()

    if request.method == "POST":
        task.text     = request.form.get("task", task.text).strip()
        task.priority = request.form.get("priority", task.priority)
        due_str       = request.form.get("due_date", "").strip()
        task.due_date = datetime.strptime(due_str, "%Y-%m-%d").date() if due_str else None

        tag_ids  = request.form.getlist("tags")
        new_tag  = request.form.get("new_tag", "").strip()
        task.tags = []
        for tid in tag_ids:
            tag = Tag.query.get(int(tid))
            if tag:
                task.tags.append(tag)
        if new_tag:
            existing = Tag.query.filter_by(name=new_tag).first()
            if not existing:
                existing = Tag(name=new_tag, color=_random_color(new_tag))
                db.session.add(existing)
            task.tags.append(existing)

        db.session.commit()
        flash("Task updated!", "success")
        return redirect(url_for("index"))

    return render_template("edit.html", task=task, all_tags=all_tags,
                           today=date.today().isoformat())


@app.route("/clear-done")
def clear_done():
    Task.query.filter_by(done=True).delete()
    db.session.commit()
    flash("Cleared all completed tasks.", "info")
    return redirect(url_for("index"))


@app.route("/tags/delete/<int:tag_id>")
def delete_tag(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    db.session.delete(tag)
    db.session.commit()
    return redirect(url_for("index"))

@app.route("/health")
def health():
    return {"status": "ok"}, 200

# ── Helpers ────────────────────────────────────────────────────────────────────

def _random_color(seed: str) -> str:
    colors = ["#4dabf7","#69db7c","#ffa94d","#da77f2","#f783ac","#63e6be","#74c0fc","#ffe066"]
    return colors[sum(ord(c) for c in seed) % len(colors)]


# ── Init ───────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)