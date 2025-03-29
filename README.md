# Badgey Quiz Dashboard

A web-based dashboard for managing the Badgey Discord Quiz Bot.

## Features

- **Discord OAuth2 Authentication**: Secure login using Discord accounts
- **Quiz Management**: Create, edit, and delete quizzes and questions
- **User-Friendly Interface**: Modern responsive design
- **Analytics**: Detailed statistics on quiz usage and performance
- **User Management**: Control access and permissions for different users
- **Explanation Support**: Add explanations for incorrect answers

## Technology Stack

- **Backend**: Flask (Python)
- **Frontend**: Bootstrap 5, Chart.js
- **Database**: MySQL (shared with Badgey Discord Bot)
- **Authentication**: Discord OAuth2
- **Deployment**: Docker

## Prerequisites

- Python 3.8+
- MySQL/MariaDB database
- Discord application with OAuth2 setup
- Docker (for containerized deployment)

## Installation

### Local Development

1. **Clone the repository**

```bash
git clone https://github.com/yourusername/badgey-dashboard.git
cd badgey-dashboard
```

2. **Create a virtual environment**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Create a `.env` file in the project root**

```
# Flask settings
SECRET_KEY=your_secret_key
PORT=5000

# Database settings
DBHOST=localhost
DBPORT=3306
DBUSER=root
DBPASSWORD=your_db_password
DBNAME=badgey

# Discord OAuth settings
DISCORD_CLIENT_ID=your_discord_client_id
DISCORD_CLIENT_SECRET=your_discord_client_secret
DISCORD_REDIRECT_URI=http://localhost:5000/auth/callback
```

5. **Initialize the dashboard user table**

```bash
flask init-db
```

6. **Run the application**

```bash
flask run
```

The application will be available at http://localhost:5000

## Docker Deployment

### Amazon EC2 Deployment

1. **Connect to your EC2 instance** via SSH:
   ```
   ssh -i /path/to/your-key.pem ec2-user@your-ec2-ip
   ```

2. **Install Docker** (if not already installed):
   ```
   sudo yum update -y
   sudo amazon-linux-extras install docker -y
   sudo service docker start
   sudo systemctl enable docker
   sudo usermod -a -G docker ec2-user
   ```
   (Log out and back in to apply the group changes)

3. **Clone the repository**:
   ```
   git clone https://github.com/yourusername/badgey-dashboard.git
   cd badgey-dashboard
   ```

4. **Create the .env file**:
   ```
   touch .env
   nano .env
   ```

   Add the following content to the .env file (replace with your values):
   ```
   # Flask settings
   SECRET_KEY=your_secret_key
   PORT=5000
   
   # Database settings
   DBHOST=your_db_host
   DBPORT=3306
   DBUSER=your_db_user
   DBPASSWORD=your_db_password
   DBNAME=badgey
   
   # Discord OAuth settings
   DISCORD_CLIENT_ID=your_discord_client_id
   DISCORD_CLIENT_SECRET=your_discord_client_secret
   DISCORD_REDIRECT_URI=https://your-ec2-domain/auth/callback
   ```

5. **Build the Docker image**:
   ```
   docker build -t badgey-dashboard .
   ```

6. **Run the Docker container**:
   ```
   docker run -d -p 80:5000 --env-file .env --name badgey-dashboard badgey-dashboard
   ```

7. **Initialize the database** (first time only):
   ```
   docker exec -it badgey-dashboard flask init-db
   ```

8. **Access the dashboard**:
   You can now access your dashboard at `http://your-ec2-public-ip`

### Environment Variables

Getting the values for your `.env` file:

1. **SECRET_KEY**: Generate a random secure string 
   ```
   python -c "import secrets; print(secrets.token_hex(16))"
   ```

2. **Database settings**:
   - If using a local database on EC2: Use DBHOST=localhost
   - If using AWS RDS: Use the RDS endpoint from the AWS console
   - Create a database user with password using MySQL commands
   - Create a database named "badgey"

3. **Discord OAuth settings**:
   - Go to the [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a new application or select your existing Badgey bot
   - Copy the "Client ID" and "Client Secret" from OAuth2 section
   - Add a redirect URL like `http://your-ec2-ip/auth/callback`
   - Enable "identify" and "email" OAuth2 scopes

### Production Considerations

1. **HTTPS Setup**: For production, you should use HTTPS:
   - Set up an Elastic Load Balancer with SSL
   - Or use Nginx with Let's Encrypt certificates

2. **Database**: Consider using AWS RDS for your database in production

3. **Monitoring**: Set up CloudWatch for monitoring your EC2 instance

## User Roles

- **Admin**: Full access to all features
- **Quiz Creator**: Can create and manage their own quizzes
- **Quiz Editor**: Can edit existing quizzes
- **Analytics Viewer**: Can view analytics data
- **Community Manager**: Combined permissions for managing quizzes and users

## Troubleshooting

Common issues and solutions:

1. **Missing Python modules**: Ensure your requirements.txt includes all dependencies
   ```
   pip freeze > requirements.txt
   ```

2. **Docker container crash**: Check logs with 
   ```
   docker logs badgey-dashboard
   ```

3. **Database connection issues**: Verify database connection settings and ensure the database is accessible from the EC2 instance

4. **Discord authentication error**: Ensure your OAuth redirect URI matches exactly what's configured in the Discord Developer Portal

## Development

### Project Structure

```
badgey-dashboard/
├── app.py              # Main Flask application
├── models/             # Database models
├── routes/             # Route blueprints 
├── static/             # Static assets
│   ├── css/            # CSS files
│   └── js/             # JavaScript files
├── templates/          # HTML templates
│   ├── analytics/      # Analytics page templates
│   ├── quizzes/        # Quiz management templates
│   └── admin/          # Admin templates
├── requirements.txt    # Python dependencies
└── .env                # Environment variables
```

## License

This project is licensed under the MIT License.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
 
