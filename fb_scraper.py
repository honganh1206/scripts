import requests
import pandas as pd
import time
import json
import os
from datetime import datetime

class SocialMediaScraper:
    def __init__(self, access_token, group_id):
        """
        Initialize the scraper with your access token and target group ID
        
        Parameters:
        access_token (str): Your API access token
        group_id (str): ID of the group to scrape
        """
        self.access_token = access_token
        self.group_id = group_id
        self.base_url = "https://graph.facebook.com/v22.0"
        self.headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        
    def get_person_posts(self, person_id, limit=100, since_date=None):
        """
        Get all posts by a specific person in the group
        """
    # Change this line to access the feed through a different endpoint
        endpoint = f"{self.base_url}/{self.group_id}/feed"
    
    # Add more specific permissions to the request
        params = {
        "limit": 100,
        "fields": "id,message,created_time,from",
        "access_token": self.access_token  # Explicitly include the token in params
        }
        
        if since_date:
            since_timestamp = int(datetime.strptime(since_date, "%Y-%m-%d").timestamp())
            params["since"] = since_timestamp
        
        all_posts = []
        next_page = None
        
        while True:
            if next_page:
                response = requests.get(next_page, headers=self.headers)
            else:
                response = requests.get(endpoint, params=params, headers=self.headers)
            
            if response.status_code != 200:
                print(f"Error fetching posts: {response.text}")
                break
                
            data = response.json()
            
            # Filter for posts by the specific person
            person_posts = [post for post in data.get('data', []) 
                          if post.get('from', {}).get('id') == person_id]
            
            all_posts.extend(person_posts)
            
            # Check if we've reached the limit
            if len(all_posts) >= limit:
                all_posts = all_posts[:limit]
                break
                
            # Check for next page
            if 'paging' in data and 'next' in data['paging']:
                next_page = data['paging']['next']
            else:
                break
                
            # Respect rate limits
            time.sleep(1)
            
        return all_posts
    
    def get_post_reactions(self, post_id):
        """
        Get all reactions for a specific post
        
        Parameters:
        post_id (str): ID of the post
        
        Returns:
        list: List of reaction objects with user information
        """
        endpoint = f"{self.base_url}/{post_id}/reactions"
        
        params = {
            "fields": "id,name,type",
            "limit": 100
        }
        
        all_reactions = []
        next_page = None
        
        while True:
            if next_page:
                response = requests.get(next_page, headers=self.headers)
            else:
                response = requests.get(endpoint, params=params, headers=self.headers)
                
            if response.status_code != 200:
                print(f"Error fetching reactions: {response.text}")
                break
                
            data = response.json()
            all_reactions.extend(data.get('data', []))
                
            # Check for next page
            if 'paging' in data and 'next' in data['paging']:
                next_page = data['paging']['next']
            else:
                break
                
            # Respect rate limits
            time.sleep(1)
            
        return all_reactions
    
    def collect_person_post_data(self, person_id, since_date=None, output_file="post_data.xlsx"):
        """
        Collect all data about a person's posts and who reacted to them
        
        Parameters:
        person_id (str): ID of the person whose posts you want to analyze
        since_date (str): Only fetch posts after this date (format: YYYY-MM-DD)
        output_file (str): Filename to save the data
        
        Returns:
        DataFrame: Pandas DataFrame with the collected data
        """
        print(f"Collecting posts for person ID: {person_id}")
        posts = self.get_person_posts(person_id, since_date=since_date)
        print(f"Found {len(posts)} posts")
        
        all_data = []
        
        for i, post in enumerate(posts):
            post_id = post.get('id')
            print(f"Processing post {i+1}/{len(posts)}: {post_id}")
            
            # Get reactions for this post
            reactions = self.get_post_reactions(post_id)
            
            # Group reactions by type
            reaction_counts = {}
            reaction_people = {}
            
            for reaction in reactions:
                reaction_type = reaction.get('type', 'UNKNOWN')
                person_name = reaction.get('name', 'Unknown')
                
                if reaction_type not in reaction_counts:
                    reaction_counts[reaction_type] = 0
                    reaction_people[reaction_type] = []
                    
                reaction_counts[reaction_type] += 1
                reaction_people[reaction_type].append(person_name)
            
            # Create a record for this post
            post_data = {
                'post_id': post_id,
                'message': post.get('message', '')[:100] + '...' if len(post.get('message', '')) > 100 else post.get('message', ''),
                'created_time': post.get('created_time'),
                'total_reactions': len(reactions)
            }
            
            # Add reaction counts by type
            for reaction_type, count in reaction_counts.items():
                post_data[f'{reaction_type.lower()}_count'] = count
                post_data[f'{reaction_type.lower()}_people'] = ', '.join(reaction_people[reaction_type])
            
            all_data.append(post_data)
            
            # Respect rate limits
            time.sleep(1)
        
        # Convert to DataFrame
        df = pd.DataFrame(all_data)
        
        # Save to Excel
        if output_file.endswith('.xlsx'):
            df.to_excel(output_file, index=False)
            print(f"Data saved to {output_file}")
        else:
            # Save as JSON if not Excel
            with open(output_file, 'w') as f:
                json.dump(all_data, f, indent=2)
            print(f"Data saved to {output_file}")
            
        return df

# Example usage
if __name__ == "__main__":
    # Replace these with your actual credentials and IDs
    ACCESS_TOKEN = "EAAXEZCXeIW1IBO9LdgRmw76yhZACqpwZAeMi1TjST093gvVIAhiPZCekTnsHIFOVZC0hxytrWavfumP8AZCwV9ZBk2g6DM7ZA1FhZA1ZAno36BtWMNMmGfTGeF0pVYFkoqhc6PGyDPmpS0m1MsH2ApqGfahzMZBORVfoiGOA7IpZCTvMF6ZByATsPa8WvkaG82h3mQx0jBUsOkwnvDEBd6LxLbMYSBT1ZBV6msRENoHQZDZD"
    GROUP_ID = "2028891524003960"
    PERSON_ID = "1257436675203858"
    
    # You can get these IDs from the URLs in your browser
    # Group ID is typically in the URL: facebook.com/groups/YOUR_GROUP_ID
    # Person ID can be found using various methods like viewing page source
    
    scraper = SocialMediaScraper(ACCESS_TOKEN, GROUP_ID)
    
    # Get posts from the last 30 days
    from datetime import datetime, timedelta
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    # Run the collector
    data = scraper.collect_person_post_data(
        person_id=PERSON_ID,
        since_date=thirty_days_ago,
        output_file="person_post_analysis.xlsx"
    )
    
    print("Data collection complete!")
    print(f"Total posts analyzed: {len(data)}")
    if len(data) > 0:
        print(f"Most reactions on a post: {data['total_reactions'].max()}")
        most_popular = data.loc[data['total_reactions'].idxmax()]
        print(f"Most popular post preview: {most_popular['message']}")
