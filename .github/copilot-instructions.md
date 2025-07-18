<!-- Use this file to provide workspace-specific custom instructions to Copilot. For more details, visit https://code.visualstudio.com/docs/copilot/copilot-customization#_use-a-githubcopilotinstructionsmd-file -->

# Ollama Chatbot Project Instructions

This is a Flask-based chatbot web application that integrates with Ollama LLM models running locally on Raspberry Pi 5. 

## Project Architecture

- **Backend**: Python Flask with Socket.IO for real-time streaming
- **Database**: SQLAlchemy with SQLite (models: User, ChatSession, ChatMessage, ModelRating)
- **Frontend**: Bootstrap 5 with vanilla JavaScript and Socket.IO client
- **Authentication**: Flask-Login with bcrypt password hashing
- **Production**: Gunicorn with Eventlet workers for WebSocket support
- **AI Integration**: Ollama API for local LLM inference

## Key Features to Consider

- Real-time streaming chat responses using WebSocket
- Multi-model support (Llama2, Mistral, Phi, etc.)
- User authentication and session management
- Admin dashboard with statistics and model performance metrics
- Rating system for AI responses (1-5 stars)
- Chat history persistence per user
- Admin-only data access and export functionality

## Development Guidelines

1. **Security**: Always check user authentication and admin privileges for sensitive operations
2. **Real-time**: Use Socket.IO for all real-time features (chat streaming, notifications)
3. **Database**: Use SQLAlchemy ORM with proper relationships and foreign keys
4. **Error Handling**: Implement proper error handling for Ollama API failures
5. **Responsive Design**: Use Bootstrap components for mobile-friendly UI
6. **Performance**: Consider memory usage on Raspberry Pi 5 (limited resources)

## File Structure

- `app.py` - Main Flask application with routes and Socket.IO handlers
- `models.py` - SQLAlchemy database models
- `forms.py` - WTForms for user input validation
- `templates/` - Jinja2 HTML templates with Bootstrap styling
- `gunicorn.conf.py` - Production server configuration
- `start_server.sh` - Deployment script for Raspberry Pi

## API Integration

- Ollama API endpoint: `http://localhost:11434`
- Streaming responses: `/api/generate` with `stream: true`
- Model management: `/api/tags` for available models
- Error handling for network timeouts and model availability

## Testing Considerations

- Test on Raspberry Pi 5 hardware constraints
- Verify WebSocket connections work properly
- Test with multiple concurrent users
- Validate admin access controls
- Check model loading and response streaming
