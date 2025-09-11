# 🎬 Upcoming Movies for Kometa

**UMFK** (Upcoming Movies for Kometa) creates a 'coming soon' collection in your Plex server. It accomplishes this by
-  checking [Radarr](https://radarr.video/) for upcoming (monitored) movies that will release within x days.
-  creating placeholders video files in special {edition-Coming Soon} folders so the movies get picked up by Plex.
-  creating collection and overlay .yml files which can be used with [Kometa](https://kometa.wiki/en/latest/) (formerly Plex Meta Manager).

>[!note]
> UMFK uses Plex's 'editions' feature which requires a Plex Pass subscription for Server admin account.

<sub>See also [Upcoming TV Shows for Kometa](https://github.com/netplexflix/Upcoming-TV-Shows-for-Kometa)</sub>

## Example:
Default:<br>
<img width="971" height="360" alt="Image" src="https://github.com/user-attachments/assets/0017063c-2147-41ec-9430-3ecef82ef16d" />

red_frame:<br>
<img width="777" height="356" alt="Image" src="https://github.com/user-attachments/assets/588ff92e-ac42-4d80-9d3a-31eac52a7961" />

---
## 🛠️ Installation


### 1️⃣ Clone the repository:
   ```bash
   git clone https://github.com/netplexflix/Upcoming-Movies-for-Kometa.git
   cd Upcoming-Movies-for-Kometa
```

>[!TIP]
>If you don't know what that means, then simply download the script by pressing the green 'Code' button above and then 'Download Zip'.  
>Extract the files to your desired folder.

### 2️⃣ Install Python dependencies:
- Ensure you have [Python](https://www.python.org/downloads/) installed (`>=3.11`).
- Open a Terminal in the script's directory
>[!TIP]
>Windows Users:  
>Go to the UMFK folder (where UMFK.py is). Right mouse click on an empty space in the folder and click Open in Windows Terminal.
- Install the required dependencies by running:
```sh
pip install -r requirements.txt
```

## ⚙️ Configuration

Rename `config.example.yml` to `config.yml` and update your settings:

#### <ins>Radarr Configuration:</ins>
- **radarr_url**: Change if needed
- **radarr_api_key**: Can be found in Radarr under settings => General => Security.

#### <ins>General:</ins>
- **utc_offset:** Set the [UTC timezone](https://en.wikipedia.org/wiki/List_of_UTC_offsets) offset. e.g.: LA: -8, New York: -5, Amsterdam: +1, Tokyo: +9, etc
>[!NOTE]
> Some people may run their server on a different timezone (e.g. on a seedbox), therefor the script doesn't convert the air dates to your machine's local timezone. Instead, you can enter the utc offset you desire.
- **future_days_upcoming_movies**: within how many days the release has to be
- **future_only**: set to `false` (default) to also include movies that have already been released but not yet downloaded
- **include_inCinemas**: set to `true` to include cinema release dates, `false` (default) to only consider digital/physical releases
- **debug**: set to true to troubleshoot problems
- **cleanup**: set to true (default) to automatically remove placeholder folders when the actual movies are downloaded

#### <ins>path mapping</ins>
Add path mapping if needed, for example if you're using unRAID.

#### <ins>.yml settings:</ins>
The other settings allow you to customize the output of the collection and overlay .yml files.

There are two different overlays:
1. For movies with a release date in the future. This overlay will append the release date.
2. For movies that have already been released but haven't been downloaded yet. Depending on your setup there could be some time between the official release and when it's actually added to your Plex server. Since the release date is in the past it isn't printed. Instead you can state it's "coming soon". You can disable this category by setting `future_only` to `true`

>[!NOTE]
> These are date formats you can use:<br/>
> `d`: 1 digit day (1)<br/>
> `dd`: 2 digit day (01)<br/>
> `ddd`: Abbreviated weekday (Mon)<br/>
> `dddd`: Full weekday (Monday)<br/>
><br/>
> `m`: 1 digit month (1)<br/>
> `mm`: 2 digit month (01)<br/>
> `mmm`: Abbreviated month (Jan)<br/>
> `mmmm`: Full month (January)<br/>
><br/>
> `yy`: Two digit year (25)<br/>
> `yyyy`: Full year (2025)
>
>Dividers can be `/`, `-` or a space

## 📼 Placeholder video
The script will use the `UMFK` video file in the `video` subfolder.
It's a simple intro video that shows 'coming soon':

![Image](https://github.com/user-attachments/assets/588618dc-86f2-4e0f-9be7-93c5eacef4e7)

You can replace this with any video you like, as long as it is named `UMFK`.

## ☄️ Add the collection and overlay files to your Kometa config

Open your **Kometa** config.yml (typically at `Kometa/config/config.yml`) and add the path to the UMFK .yml files under `collection_files` and `overlay_files`

Example:
```yaml
Movies:
  collection_files:
    - file: P:/scripts/UMFK/Kometa/UMFK_MOVIES_UPCOMING_COLLECTION.yml
  overlay_files:
    - file: P:/scripts/UMFK/Kometa/UMFK_MOVIES_UPCOMING_OVERLAYS.yml
```

---

## 🚀 Usage - Running the Script

Open a Terminal in your script directory and launch the script with:
   ```bash
   python UMFK.py
   ```

---

## 💡TIP: Prevent these movies from showing up under "Recently Added/Released Movies"
This script will add movies to Plex with only a placeholder video since they aren't actually out yet. You probably want to avoid seeing them pop up in your "Recently Added Movies" section on your home screen because you and/or your users will think it's actually available already.
To accomplish this I strongly recommend replacing the default "Recently Added Movies" collection with your own smart collection:

1. Go to your Movie library
2. Sort by "by Date Added"
3. Press the '+' burger menu icon on the right then click "create smart collection"
4. Add filter `Label` `is not` `Coming Soon` (or whatever you used as collection_name. Since the collection yml uses smart_label, Kometa adds that label to the relevant movies, so you can exclude these shows based on that label. The label will be automatically removed by Kometa once the actual movie is downloaded)
5. Press 'Save As' > 'Save As Smart Collection'
6. Name it something like "New in Movies🎞️"
7. In the new collection click the three dots then "Visible on" > "Home"
8. Go to Settings > under 'manage' click 'Libraries' > Click on "Manage Recommendations" next to your Movie library
9. Unpin the default "Recently Added Movies" and "Recently Released Movies" from home, and move your newly made smart collection to the top (or wherever you want it)

You have now replaced the default home categories with your own, more flexible one that excludes these 'dummy' movies that are not actually out yet.
You can do loads of other things with it this way. For example manually apply an exclude label to certain individual movies you don't want to show up in this home banner.

## 💡TIP2: Understanding Release Types
UMFK can handle different types of movie releases:

Digital Release: When the movie becomes available on digital platforms (streaming, VOD)
Physical Release: When the movie is released on Blu-ray/DVD
Cinema Release: When the movie is released in theaters

By default, UMFK only considers Digital and Physical releases (include_inCinemas: false). If you want to include cinema releases as well, set include_inCinemas: true in your config. When multiple release dates are available, UMFK will use the earliest one.

---

### ⚠️ **Do you Need Help or have Feedback?**
- Join the [Discord](https://discord.gg/VBNUJd7tx3).

  
---  
### ❤️ Support the Project
If you like this project, please ⭐ star the repository and share it with the community!

<br/>

[!["Buy Me A Coffee"](https://github.com/user-attachments/assets/5c30b977-2d31-4266-830e-b8c993996ce7)](https://www.buymeacoffee.com/neekokeen)
