from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
from models import User

class LoginForm(FlaskForm):
    username_email = StringField('Username or Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Authenticate')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=50)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    name = StringField('Full Name', validators=[DataRequired()])
    role = SelectField('Role', choices=[('member', 'Member'), ('admin', 'Administrator')])
    profile_pic = FileField('Profile Picture', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])
    submit = SubmitField('Register Member')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Username already taken.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already registered.')

class AnnouncementForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    type = SelectField('Type', choices=[('General', 'General'), ('Urgent', 'Urgent'), ('Meeting', 'Meeting'), ('Private', 'Private')])
    content = TextAreaField('Content', validators=[DataRequired()])
    is_pinned = BooleanField('Pin to Dashboard')
    submit = SubmitField('Post Announcement')

class MessageForm(FlaskForm):
    recipient_id = SelectField('Recipient', coerce=int, validators=[DataRequired()])
    content = TextAreaField('Message', validators=[DataRequired()])
    attachment = FileField('Attachment', validators=[FileAllowed(['jpg', 'png', 'jpeg', 'pdf', 'docx', 'txt'])])
    submit = SubmitField('Send Message')

class SettingsForm(FlaskForm):
    name = StringField('Display Name', validators=[DataRequired()])
    new_password = PasswordField('New Password (Optional)', validators=[Length(min=6, max=100)], render_kw={"placeholder": "Leave blank to keep current"})
    profile_pic = FileField('Update Profile Picture', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])
    submit = SubmitField('Update Profile')
