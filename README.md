SteamVRMQTT
===========

This python program sends information from SteamVR via MQTT to home automation systems. It's designed to work with Home Assistant's [MQTT auto discovery](https://www.home-assistant.io/docs/mqtt/discovery/), but should work just fine with any other MQTT enabled automation system.

Current information that is sent is:
* Whether SteamVR is running
* Whether headset is worn
* Current game being played

The following settings can also be controlled:
* Display brightness
* Floor bounds visible
* Center marker visible
