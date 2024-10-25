### How to use JITStreamer with Docker

This is somewhat still a work in progress, but it has been tested and works as it's currently is made. Improvements like a smaller image and less privileges are planned as TODO.

Make sure port 8080 is free first; then you can get the container with:
```bash
docker run -it --rm -v ${PWD}/:/root/.pymobiledevice3/ -v /var/run:/var/run --cap-add=NET_ADMIN --network=host ghcr.io/stossy11/jitstreamer-2.0 --pair
```

In the directory you've started this command you'll find your .plist file aswell as the Xcode_iOS_DDI_Personalized directory JITStreamer uses. Don't remove those but copy the .plist to you're device (and copy it's name while you're at it).

Once you've gone through the shortcut and got it working, you can close by doing: CRLT + C. You're container get's cleaned up but you can start it in the background and on boot this time by using:

```bash
docker run -d --name jitstreamer-2.0 --restart=always -v ${PWD}/:/root/.pymobiledevice3/ -v /var/run:/var/run --cap-add=NET_ADMIN --network=host ghcr.io/stossy11/jitstreamer-2.0
```

#### Use JITStreamer with Wireguard (docker-compose)

This chapter resumes from the chapter above, this will make it possible to quickly get a VPN container which you can use to reach your JITStreamer-2.0 server to enable JIT everywhere.

Make sure to stop your current JITStreamer-2.0 container. You can stop and remove it with: `docker stop jitstreamer-2.0` and `docker rm jitstreamer-2.0`.

Download the docker-compose.yml file to your current directory (where you also have the Xcode_iOS_DDI_Personalized folder and the .plist file):
```bash
wget https://raw.githubusercontent.com/stossy11/JITStreamer-2.0/refs/heads/main/docker-compose.yml
```

Next you need to create hash for the password you'll need to log into the wireguard dashboard:
```bash
docker run -it ghcr.io/wg-easy/wg-easy wgpw YOUR_PASSWORD
```
Change YOUR_PASSWORD with a password of your choosing.

The output of this command should look something like this: `PASSWORD_HASH='$2a$12$LZzYTKWwblEwpdF66R9pfemHlEbTJd9D9ishWYXTtdR812sjd0H8u'`

Copy and edit this line to remove the single quote's (') and for each dollar sign ($) add a second after it `($$)`. You're line should look something like this: `PASSWORD_HASH=$$2a$$12$$LZzYTKWwblEwpdF66R9pfemHlEbTJd9D9ishWYXTtdR812sjd0H8u`

Copy this line and edit the docker-compose.yml file. Replace the PASSWORD_HASH=replaceme field with yours.

Next fill in the WG_HOST variable with your public IP. You can find this by visiting or running this command: 
```bash
curl -s https://ipv4.icanhazip.com/
```

Lastly, fill in the WG_ALLOWED_IPS variable with your host IP. You can find this by running this command: 
```bash
hostname -I | cut -f1 -d' ' 
```
or look for your host IP with the command: `ip a`.

Now that's all filled in, you can save and exit.

To run your containers in a detached state, run the following command:
```bash
docker-compose up -d
``` 
If you don't have docker-compose, you can get it by installing this package with your package manager `(apt/dnf/apk install): docker-compose-plugin` .

Now you can visit your host IP on port 51821. Log into wireguard with your password, create a new client and install wireguard on your iDevice if you haven't already. Add a config within your Wireguard app and use the scan QR option to transfer the config to your iDevice.

Turn on the vpn and you should be able to enable JIT everywhere. You can test this by disconnecting from your home Wi-Fi and enabeling an app with JIT.

Containers are pre-configured to start on boot.
You're wireguard config is stored in: `~/.wg-easy/` with root permissions.
