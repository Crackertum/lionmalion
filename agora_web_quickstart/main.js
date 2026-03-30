import AgoraRTC from "agora-rtc-sdk-ng";

let rtc = {
    localAudioTrack: null,
    localVideoTrack: null,
    client: null,
};

let options = {
    appId: "1cf430a72a294d1ea1638e4054944d31",
    channel: "lion_coordination",
    token: null, // Pass null for testing if tokens are disabled in console
    uid: 0,
};

async function startBasicCall() {
    rtc.client = AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });

    rtc.client.on("user-published", async (user, mediaType) => {
        await rtc.client.subscribe(user, mediaType);
        console.log("Remote user subscribed:", user.uid);

        if (mediaType === "video") {
            const remotePlayerContainer = document.createElement("div");
            remotePlayerContainer.id = user.uid.toString();
            remotePlayerContainer.className = "video-container";
            remotePlayerContainer.innerHTML = `<div class="video-label">REMOTE USER ${user.uid}</div>`;
            document.getElementById("remote-playerlist").append(remotePlayerContainer);
            user.videoTrack.play(remotePlayerContainer);
        }

        if (mediaType === "audio") {
            user.audioTrack.play();
        }
    });

    rtc.client.on("user-unpublished", (user) => {
        const remotePlayerContainer = document.getElementById(user.uid.toString());
        if (remotePlayerContainer) remotePlayerContainer.remove();
    });

    // Join the channel
    const uid = await rtc.client.join(options.appId, options.channel, options.token, options.uid);
    console.log("Joined with UID:", uid);

    // Create and publish local tracks
    rtc.localAudioTrack = await AgoraRTC.createMicrophoneAudioTrack();
    rtc.localVideoTrack = await AgoraRTC.createCameraVideoTrack();
    
    // Play local video
    rtc.localVideoTrack.play("local-player");
    
    // Publish tracks
    await rtc.client.publish([rtc.localAudioTrack, rtc.localVideoTrack]);
    console.log("Local tracks published!");

    document.getElementById("join").disabled = true;
    document.getElementById("leave").disabled = false;
}

async function leaveCall() {
    rtc.localAudioTrack.close();
    rtc.localVideoTrack.close();

    // Traverse all remote users and remove their containers
    rtc.client.remoteUsers.forEach(user => {
        const playerContainer = document.getElementById(user.uid.toString());
        playerContainer && playerContainer.remove();
    });

    await rtc.client.leave();
    console.log("Left channel.");

    document.getElementById("join").disabled = false;
    document.getElementById("leave").disabled = true;
}

document.getElementById("join").onclick = async () => {
    try {
        await startBasicCall();
    } catch (err) {
        console.error("Join call failed:", err);
    }
};

document.getElementById("leave").onclick = async () => {
    await leaveCall();
};
