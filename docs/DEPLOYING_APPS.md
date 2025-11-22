# Deploying Apps on Android with proot-distro

Since Docker/LXC/Podman are blocked by DNS issues and PIE enforcement, the most practical solution is **proot-distro** - a tool that creates full Linux distributions in userspace without requiring containers.

## Why proot-distro?

- ✅ **Works immediately** - No compilation needed
- ✅ **No network required** - Uses cached rootfs
- ✅ **Full Linux environment** - Run any Linux app
- ✅ **No kernel requirements** - Works on stock kernels
- ✅ **Can run Docker inside** - Nested containerization possible

## Installation

### Step 1: Install proot-distro in Termux

```bash
# Open Termux
pkg install proot-distro
```

**If DNS fails**, download the package manually:
1. On another device with internet, download from: https://packages.termux.dev/
2. Transfer to your phone
3. Install: `pkg install /path/to/proot-distro.deb`

### Step 2: Install a Linux Distribution

```bash
# List available distributions
proot-distro list

# Install Ubuntu (recommended)
proot-distro install ubuntu

# Or install Debian
proot-distro install debian

# Or install Alpine (lightweight)
proot-distro install alpine
```

### Step 3: Launch Your Linux Environment

```bash
# Login to Ubuntu
proot-distro login ubuntu

# You're now in a full Ubuntu environment!
```

## Deploying Your Apps

### Node.js Applications

```bash
# Inside proot-distro Ubuntu
apt update
apt install nodejs npm

# Deploy your app
cd /path/to/your/app
npm install
npm start
```

### Python Applications

```bash
# Inside proot-distro
apt install python3 python3-pip

# Deploy your app
cd /path/to/your/app
pip3 install -r requirements.txt
python3 app.py
```

### Docker Applications (Nested)

```bash
# Inside proot-distro
apt update
apt install docker.io

# Start Docker daemon
dockerd &

# Run your containers
docker run -d nginx
docker-compose up
```

### Database Services

```bash
# PostgreSQL
apt install postgresql
service postgresql start

# MySQL
apt install mysql-server
service mysql start

# Redis
apt install redis-server
service redis-server start

# MongoDB
apt install mongodb
service mongodb start
```

### Web Servers

```bash
# Nginx
apt install nginx
service nginx start

# Apache
apt install apache2
service apache2 start
```

## Accessing Your Apps

### From Android

Apps running in proot-distro are accessible via localhost:

```bash
# If your app runs on port 3000
# Access from Android browser: http://localhost:3000
```

### From Network

To access from other devices:

```bash
# Find your device IP
ip addr show wlan0

# Access from network: http://YOUR_DEVICE_IP:3000
```

## File Sharing

### Android → proot-distro

```bash
# Android storage is mounted at /sdcard
cd /sdcard
# Your files are accessible here
```

### proot-distro → Android

```bash
# Copy files to /sdcard
cp myfile.txt /sdcard/Download/
```

## Running Services on Boot

### Create a startup script

```bash
# In Termux (not proot)
nano ~/start-services.sh
```

Add:
```bash
#!/data/data/com.termux/files/usr/bin/bash
proot-distro login ubuntu -- bash -c "
    service postgresql start
    service nginx start
    cd /home/myapp && npm start
"
```

Make executable:
```bash
chmod +x ~/start-services.sh
```

### Auto-start with Termux:Boot

1. Install Termux:Boot from F-Droid
2. Create `~/.termux/boot/start-services.sh`
3. Services start automatically on device boot

## Docker Compose Example

```yaml
# docker-compose.yml
version: '3'
services:
  web:
    image: nginx
    ports:
      - "8080:80"
  
  app:
    image: node:18
    volumes:
      - ./app:/usr/src/app
    command: npm start
  
  db:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: password
```

Run:
```bash
# Inside proot-distro
docker-compose up -d
```

## Performance Tips

### 1. Use Alpine for Lightweight Apps
```bash
proot-distro install alpine
# Alpine uses much less RAM and storage
```

### 2. Limit Resource Usage
```bash
# Set memory limit for processes
ulimit -m 1000000  # 1GB
```

### 3. Use tmpfs for Temporary Files
```bash
# Mount tmpfs for faster I/O
mount -t tmpfs tmpfs /tmp
```

## Troubleshooting

### "Command not found" in proot

```bash
# Make sure you're logged into proot
proot-distro login ubuntu

# Check PATH
echo $PATH
```

### Services Won't Start

```bash
# Some services need special handling in proot
# Use direct commands instead of service:

# Instead of: service nginx start
# Use: nginx

# Instead of: service postgresql start
# Use: su - postgres -c "pg_ctl start"
```

### Permission Denied

```bash
# proot runs as your user, not root
# Some operations may fail
# Workaround: use fakeroot

apt install fakeroot
fakeroot bash
# Now you have fake root privileges
```

## Advantages Over Docker

1. **No PIE issues** - Runs in userspace
2. **No kernel requirements** - Works on any Android
3. **Full system access** - Can modify anything
4. **Persistent** - Changes are saved
5. **Multiple distros** - Run Ubuntu, Debian, Alpine simultaneously

## Limitations

1. **No real isolation** - Not as secure as containers
2. **Slower than native** - Some overhead from proot
3. **No cgroups** - Can't limit resources like Docker
4. **Some syscalls fail** - Advanced features may not work

## Comparison

| Feature | Docker | proot-distro |
|---------|--------|--------------|
| Isolation | ✅ Strong | ⚠️ Weak |
| Performance | ✅ Native | ⚠️ Slight overhead |
| Setup | ❌ Complex | ✅ Simple |
| Works on Android | ❌ PIE issues | ✅ Always |
| Resource limits | ✅ cgroups | ❌ None |
| Ease of use | ⚠️ Medium | ✅ Easy |

## Conclusion

For deploying apps on Android, **proot-distro is the most practical solution**:
- Works immediately without fighting PIE enforcement
- Gives you a full Linux environment
- Can run most applications without modification
- Can even run Docker inside for containerized apps

The kernel you built has all the Docker features, so if you later solve the PIE issue or get proper packages, you can switch to native Docker. But for now, proot-distro will get your apps running today.

## Next Steps

1. Install proot-distro
2. Install your preferred Linux distribution
3. Deploy your applications
4. Set up auto-start scripts
5. Enjoy your apps running on Android!
