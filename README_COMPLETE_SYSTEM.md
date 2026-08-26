# 🚀 Viz.AI - Complete Connected System

A full-stack data visualization platform that connects a React frontend with a FastAPI backend, featuring a 5-stage AI pipeline for generating interactive Dash dashboards.

## 🏗️ System Architecture

```
┌─────────────────┐    HTTP/WebSocket    ┌─────────────────┐
│   React Frontend │ ◄──────────────────► │  FastAPI Backend │
│   (Next.js)     │                      │                 │
└─────────────────┘                      └─────────────────┘
                                                │
                                                ▼
                                    ┌─────────────────┐
                                    │  5-Stage AI     │
                                    │   Pipeline      │
                                    │                 │
                                    │ 1. Data Analysis│
                                    │ 2. RAG Retrieval│
                                    │ 3. Dashboard    │
                                    │    Design       │
                                    │ 4. Code Gen     │
                                    │ 5. Optimization │
                                    └─────────────────┘
                                                │
                                                ▼
                                    ┌─────────────────┐
                                    │  Generated      │
                                    │  Dash App      │
                                    │  (Port 8050+)  │
                                    └─────────────────┘
```

## 📁 Project Structure

```
viz.ai/
├── backend/                          # FastAPI Backend
│   ├── app/
│   │   ├── main.py                  # FastAPI app with endpoints
│   │   └── services/
│   │       ├── prompt_chain_new.py  # 5-stage AI pipeline
│   │       └── rag1_example_viz.json # Example dashboards
│   ├── start_backend.py             # Backend startup script
│   ├── requirements.txt              # Python dependencies
│   ├── uploads/                      # User uploaded datasets
│   └── generated_dashboards/         # Generated dashboard files
├── src/                              # React Frontend
│   ├── components/
│   │   └── DataVisualizationAgent.tsx # Main UI component
│   └── services/
│       └── api.ts                   # API service layer
└── README_COMPLETE_SYSTEM.md        # This file
```

## 🚀 Quick Start

### 1. Backend Setup

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Create environment file
echo "GROQ_API_KEY=your_groq_api_key_here" > .env.local

# Start the backend
python start_backend.py
```

The backend will be available at:
- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 2. Frontend Setup

```bash
# In a new terminal, from the project root
npm install
npm run dev
```

The frontend will be available at:
- **App**: http://localhost:3000 (or 5173)

## 🔧 How It Works

### 1. **File Upload** 📤
- User uploads CSV dataset via drag & drop or file picker
- File is stored on backend with unique ID
- Frontend receives confirmation and file ID

### 2. **Dashboard Generation** 🤖
- User enters visualization prompt
- Frontend calls backend to start generation
- Backend runs 5-stage AI pipeline:
   - **Stage 1**: Comprehensive dataset analysis
   - **Stage 2**: RAG retrieval of similar examples
   - **Stage 3**: Dashboard design specification
   - **Stage 4**: Dash code generation
   - **Stage 5**: Code optimization & error fixing

### 3. **Real-time Status** 📊
- Frontend polls backend for generation status
- User sees real-time progress updates
- Toast notifications for each stage completion

### 4. **Dashboard Execution** 🚀
- Generated code is automatically executed
- Dash app starts on available port (8050+)
- User gets direct link to running dashboard
- Frontend shows live preview controls

### 5. **Code Management** 💻
- View generated Python code in browser
- Download code for local execution
- Stop/start dashboard as needed

## 🎯 Key Features

### ✅ **Backend (FastAPI)**
- **File Management**: Secure CSV upload/storage
- **AI Pipeline**: Complete 5-stage generation
- **Dashboard Execution**: Sandboxed Dash app running
- **Port Management**: Automatic port allocation
- **Process Control**: Start/stop dashboard processes
- **API Documentation**: Auto-generated OpenAPI docs

### ✅ **Frontend (React)**
- **Modern UI**: Beautiful, responsive design
- **Real-time Updates**: Live status polling
- **File Upload**: Drag & drop CSV support
- **Code Preview**: View generated Python code
- **Dashboard Control**: Start/stop/access dashboards
- **Error Handling**: Comprehensive error management

### ✅ **AI Pipeline**
- **Dataset Analysis**: Complete data understanding
- **Smart Retrieval**: RAG-based example finding
- **Design Generation**: Comprehensive specifications
- **Code Generation**: Working Dash applications
- **Optimization**: Error-free, optimized code

## 🔌 API Endpoints

### **File Management**
- `POST /upload-dataset` - Upload CSV file
- `GET /download-dashboard/{id}` - Download generated code

### **Dashboard Generation**
- `POST /generate-dashboard` - Start AI pipeline
- `GET /dashboard-status/{id}` - Check generation status

### **Dashboard Execution**
- `POST /run-dashboard/{id}` - Start Dash app
- `GET /stop-dashboard/{id}` - Stop running dashboard

## 🎨 Frontend Components

### **DataVisualizationAgent.tsx**
- **File Upload Area**: Drag & drop CSV support
- **Prompt Input**: Natural language visualization requests
- **Status Display**: Real-time generation progress
- **Dashboard Controls**: Start/stop/access dashboards
- **Code Viewer**: Generated Python code display
- **Example Prompts**: Pre-built visualization requests

## 🛡️ Security & Safety

### **Sandboxed Execution**
- Dash apps run in isolated processes
- Automatic port allocation prevents conflicts
- Process monitoring and cleanup

### **File Validation**
- CSV-only uploads
- File size limits
- Secure file storage

### **Error Handling**
- Comprehensive error catching
- User-friendly error messages
- Graceful fallbacks

## 🚀 Deployment Considerations

### **Local Development**
- Backend: `python start_backend.py`
- Frontend: `npm run dev`
- Database: File-based storage

### **Production Deployment**
- **Backend**: Deploy FastAPI with Gunicorn/Uvicorn
- **Frontend**: Build and serve static files
- **Database**: Use proper database (PostgreSQL/MongoDB)
- **File Storage**: Cloud storage (S3, GCS)
- **Process Management**: Use systemd or Docker
- **Load Balancing**: Multiple backend instances

### **Environment Variables**
```bash
# Backend
GROQ_API_KEY=your_groq_api_key

# Frontend
NEXT_PUBLIC_API_URL=https://your-api.com
```

## 🔍 Troubleshooting

### **Common Issues**

1. **Backend won't start**
   - Check Python dependencies: `pip install -r requirements.txt`
   - Verify GROQ_API_KEY in `.env.local`
   - Check port 8000 availability

2. **Frontend can't connect**
   - Ensure backend is running on port 8000
   - Check CORS settings in backend
   - Verify API_BASE_URL in frontend

3. **Dashboard generation fails**
   - Check GROQ API key validity
   - Verify CSV file format
   - Check backend logs for errors

4. **Dashboard won't start**
   - Check if ports 8050-8060 are available
   - Verify Python dependencies for Dash
   - Check generated code for syntax errors

### **Debug Mode**
```bash
# Backend with verbose logging
python start_backend.py --log-level debug

# Frontend with console logging
# Check browser console for API calls
```

## 🎉 What You Get

### **Complete Working System**
- ✅ Full-stack data visualization platform
- ✅ AI-powered dashboard generation
- ✅ Real-time preview and execution
- ✅ Professional, modern UI
- ✅ Secure file handling
- ✅ Comprehensive error handling

### **Ready for Production**
- ✅ Scalable architecture
- ✅ API documentation
- ✅ Error handling
- ✅ Security considerations
- ✅ Deployment guides

## 🚀 Next Steps

1. **Test the System**: Upload a CSV and generate a dashboard
2. **Customize UI**: Modify frontend styling and components
3. **Add Features**: Implement user authentication, saved dashboards
4. **Scale Up**: Deploy to cloud with proper infrastructure
5. **Monitor**: Add logging, metrics, and alerting

---

**🎯 Ready to create amazing data visualizations?**

Start the backend, open the frontend, upload your CSV, and watch the AI create beautiful interactive dashboards! 🚀✨ 