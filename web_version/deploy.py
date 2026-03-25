#!/usr/bin/env python3
"""
Deployment script for Otonom Car Web Version
Supports multiple deployment platforms
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

class WebAppDeployer:
    def __init__(self):
        self.project_dir = Path(__file__).parent
        self.requirements_file = self.project_dir / "requirements.txt"
        self.docker_file = self.project_dir / "Dockerfile"
        self.compose_file = self.project_dir / "docker-compose.yml"
        
    def check_dependencies(self):
        """Check if required files exist"""
        required_files = [
            "web_app.py",
            "requirements.txt",
            "Dockerfile"
        ]
        
        missing_files = []
        for file in required_files:
            if not (self.project_dir / file).exists():
                missing_files.append(file)
        
        if missing_files:
            print(f"❌ Missing required files: {missing_files}")
            return False
        
        # Check for best.pt
        if not (self.project_dir / "best.pt").exists():
            print("⚠️  Warning: best.pt not found. YOLO detection may not work.")
            print("   Please copy your model file to the web_version directory.")
        
        return True
    
    def setup_local(self):
        """Setup for local deployment"""
        print("🔧 Setting up local deployment...")
        
        # Create virtual environment
        if not (self.project_dir / "venv").exists():
            print("📦 Creating virtual environment...")
            subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
        
        # Activate and install requirements
        if os.name == 'nt':  # Windows
            activate_script = self.project_dir / "venv" / "Scripts" / "activate.bat"
            pip_executable = self.project_dir / "venv" / "Scripts" / "pip"
        else:  # Unix
            activate_script = self.project_dir / "venv" / "bin" / "activate"
            pip_executable = self.project_dir / "venv" / "bin" / "pip"
        
        print("📥 Installing requirements...")
        subprocess.run([str(pip_executable), "install", "-r", str(self.requirements_file)], check=True)
        
        print("✅ Local setup complete!")
        print("🚀 Run with: python web_app.py")
        
    def setup_docker(self):
        """Setup for Docker deployment"""
        print("🐳 Setting up Docker deployment...")
        
        # Check if Docker is available
        try:
            subprocess.run(["docker", "--version"], check=True, capture_output=True)
            subprocess.run(["docker-compose", "--version"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("❌ Docker or Docker Compose not found. Please install Docker first.")
            return False
        
        # Build and run with Docker Compose
        print("🔨 Building Docker image...")
        subprocess.run(["docker-compose", "build"], check=True)
        
        print("🚀 Starting Docker container...")
        subprocess.run(["docker-compose", "up", "-d"], check=True)
        
        print("✅ Docker deployment complete!")
        print("📱 Access at: http://localhost:8000")
        
    def setup_cloud(self, platform="heroku"):
        """Setup for cloud deployment"""
        print(f"☁️ Setting up {platform} deployment...")
        
        if platform == "heroku":
            self.setup_heroku()
        elif platform == "railway":
            self.setup_railway()
        elif platform == "vercel":
            self.setup_vercel()
        else:
            print(f"❌ Unsupported platform: {platform}")
            return False
        
        return True
    
    def setup_heroku(self):
        """Setup for Heroku deployment"""
        print("📦 Setting up Heroku deployment...")
        
        # Create Heroku files
        heroku_files = {
            "Procfile": "web: uvicorn web_app:app --host 0.0.0.0 --port $PORT",
            "runtime.txt": "python-3.9.16"
        }
        
        for filename, content in heroku_files.items():
            file_path = self.project_dir / filename
            file_path.write_text(content)
            print(f"📄 Created {filename}")
        
        print("✅ Heroku setup complete!")
        print("🚀 Deploy with: heroku create && git push heroku main")
    
    def setup_railway(self):
        """Setup for Railway deployment"""
        print("📦 Setting up Railway deployment...")
        
        # Create railway.toml
        railway_config = """[build]
builder = "NIXPACKS"

[deploy]
startCommand = "uvicorn web_app:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/"
healthcheckTimeout = 100
restartPolicyType = "ON_FAILURE"
"""
        
        (self.project_dir / "railway.toml").write_text(railway_config)
        print("📄 Created railway.toml")
        
        print("✅ Railway setup complete!")
        print("🚀 Deploy with: railway up")
    
    def setup_vercel(self):
        """Setup for Vercel deployment"""
        print("📦 Setting up Vercel deployment...")
        
        # Create vercel.json
        vercel_config = """{
  "version": 2,
  "builds": [
    {
      "src": "web_app.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "web_app.py"
    }
  ]
}"""
        
        (self.project_dir / "vercel.json").write_text(vercel_config)
        print("📄 Created vercel.json")
        
        print("✅ Vercel setup complete!")
        print("🚀 Deploy with: vercel --prod")
    
    def run_local(self):
        """Run the web app locally"""
        print("🚀 Starting local web server...")
        
        # Check if venv exists
        if not (self.project_dir / "venv").exists():
            print("❌ Virtual environment not found. Run 'python deploy.py --setup-local' first.")
            return
        
        # Activate venv and run
        if os.name == 'nt':  # Windows
            activate_script = self.project_dir / "venv" / "Scripts" / "activate.bat"
            python_executable = self.project_dir / "venv" / "Scripts" / "python"
        else:  # Unix
            activate_script = self.project_dir / "venv" / "bin" / "activate"
            python_executable = self.project_dir / "venv" / "bin" / "python"
        
        # Run the app
        os.chdir(self.project_dir)
        subprocess.run([str(python_executable), "web_app.py"])
    
    def get_ip_address(self):
        """Get local IP address for network access"""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

def main():
    parser = argparse.ArgumentParser(description="Deploy Otonom Car Web Version")
    parser.add_argument("--setup-local", action="store_true", help="Setup local environment")
    parser.add_argument("--setup-docker", action="store_true", help="Setup Docker deployment")
    parser.add_argument("--setup-cloud", choices=["heroku", "railway", "vercel"], help="Setup cloud deployment")
    parser.add_argument("--run", action="store_true", help="Run the web app locally")
    parser.add_argument("--check", action="store_true", help="Check dependencies")
    
    args = parser.parse_args()
    
    deployer = WebAppDeployer()
    
    if args.check:
        if deployer.check_dependencies():
            print("✅ All dependencies satisfied!")
        else:
            print("❌ Dependencies missing!")
            sys.exit(1)
    
    elif args.setup_local:
        if not deployer.check_dependencies():
            sys.exit(1)
        deployer.setup_local()
    
    elif args.setup_docker:
        if not deployer.check_dependencies():
            sys.exit(1)
        deployer.setup_docker()
    
    elif args.setup_cloud:
        if not deployer.check_dependencies():
            sys.exit(1)
        deployer.setup_cloud(args.setup_cloud)
    
    elif args.run:
        deployer.run_local()
    
    else:
        # Default: show help and current status
        print("🚀 Otonom Car Web Version Deployer")
        print("=" * 50)
        
        if deployer.check_dependencies():
            print("✅ Dependencies: OK")
        else:
            print("❌ Dependencies: Missing")
        
        ip = deployer.get_ip_address()
        print(f"🌐 Local IP: {ip}")
        print(f"📱 Access: http://{ip}:8000")
        print()
        print("Usage:")
        print("  python deploy.py --check          Check dependencies")
        print("  python deploy.py --setup-local    Setup local environment")
        print("  python deploy.py --setup-docker    Setup Docker deployment")
        print("  python deploy.py --setup-cloud     Setup cloud deployment")
        print("  python deploy.py --run             Run locally")
        print()
        print("Quick start:")
        print("  python deploy.py --setup-local")
        print("  python deploy.py --run")

if __name__ == "__main__":
    main()
