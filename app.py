import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io

st.set_page_config(page_title="Gantt Chart Generator", layout="wide", page_icon="📊")

st.title("📊 Gantt Chart Generator")
st.markdown("### Tölts fel egy Excel fájlt és generálj Gantt chartot!")

# Sidebar instructions
with st.sidebar:
    st.header("ℹ️ Használati útmutató")
    st.markdown("""
    **Szükséges Excel oszlopok:**
    - `Name`: Feladat neve
    - `Start_Date`: Kezdő dátum
    - `Finish_Date`: Befejező dátum
    - `Duration`: Időtartam (pl. "5 days")
    - `Outline_Level`: Hierarchia szint (1, 2, 3, 4)
    - `Predecessors`: Előző feladatok (opcionális)
    - `Not appear`: Elrejtés (True/False)
    
    **Használat:**
    1. Töltsd fel az Excel fájlt
    2. Automatikusan generálódik a chart
    3. Töltsd le HTML formátumban
    """)

# File uploader
uploaded_file = st.file_uploader("📁 Válaszd ki az Excel fájlt", type=['xlsx', 'xls'])

def process_dataframe(df):
    """Process the dataframe for Gantt chart"""
    # Re-index
    df.index = range(1, len(df) + 1)
    
    # Convert dates
    df['Start_Date'] = pd.to_datetime(df['Start_Date'])
    df['Finish_Date'] = pd.to_datetime(df['Finish_Date'])
    
    # Extract duration
    df['Duration_days'] = df['Duration'].str.extract('(\\d+)').astype(int)
    df['Plot_Duration'] = (df['Finish_Date'] - df['Start_Date']).dt.days
    
    # Split milestones and regular tasks
    df_milestones = df[df['Duration_days'] == 0]
    df_regular = df[df['Duration_days'] != 0]
    
    # Parse predecessors
    def parse_predecessors(predecessors_str):
        if pd.isna(predecessors_str):
            return []
        try:
            predecessors = [int(p.strip()) for p in str(predecessors_str).split(',')]
            return predecessors
        except ValueError:
            return []
    
    df['Parsed_Predecessors'] = df['Predecessors'].apply(parse_predecessors)
    
    # Filter by outline levels
    selected_outline_levels = [1, 2, 3, 4]
    df_regular = df_regular[df_regular['Outline_Level'].isin(selected_outline_levels)]
    df_milestones = df_milestones[df_milestones['Outline_Level'].isin(selected_outline_levels)]
    
    # Apply collapse logic
    indices_to_hide = set()
    is_collapsing = False
    parent_outline_level = -1
    
    for original_index, row_full_df in df.iterrows():
        if row_full_df['Not appear'] == True:
            is_collapsing = True
            parent_outline_level = row_full_df['Outline_Level']
            continue
        
        if is_collapsing:
            if row_full_df['Outline_Level'] > parent_outline_level:
                indices_to_hide.add(original_index)
            else:
                is_collapsing = False
                parent_outline_level = -1
    
    df_regular = df_regular[~df_regular.index.isin(indices_to_hide)].copy()
    df_milestones = df_milestones[~df_milestones.index.isin(indices_to_hide)].copy()
    
    # Create Y labels
    df_regular['Y_Label'] = df_regular.apply(
        lambda row: '  ' * (row['Outline_Level'] - 1) + row['Name'], axis=1
    )
    df_milestones['Y_Label'] = df_milestones.apply(
        lambda row: '  ' * (row['Outline_Level'] - 1) + row['Name'], axis=1
    )
    
    return df, df_regular, df_milestones

def create_gantt_chart(df, df_regular, df_milestones):
    """Create the Gantt chart"""
    combined_filtered_df = pd.concat([df_regular, df_milestones]).sort_index()
    sorted_y_labels = combined_filtered_df['Y_Label'].drop_duplicates().tolist()
    y_label_to_pos = {label: i for i, label in enumerate(sorted_y_labels)}
    
    fig = go.Figure()
    
    # Add regular tasks
    shapes = []
    for i, row in df_regular.iterrows():
        bar_color = 'steelblue'
        if row['Outline_Level'] == 1:
            bar_color = 'black'
        elif row['Outline_Level'] == 2:
            bar_color = 'dimgray'
        elif row['Outline_Level'] == 3:
            bar_color = 'darkgray'
        
        y_pos = y_label_to_pos[row['Y_Label']]
        bar_height = 0.4
        
        shapes.append(dict(
            type="rect",
            xref="x",
            yref="y",
            x0=row['Start_Date'],
            y0=y_pos - bar_height/2,
            x1=row['Finish_Date'],
            y1=y_pos + bar_height/2,
            fillcolor=bar_color,
            line=dict(width=0),
            layer="above"
        ))
        
        fig.add_trace(go.Scatter(
            x=[(row['Start_Date'] + (row['Finish_Date'] - row['Start_Date'])/2)],
            y=[y_pos],
            mode='markers',
            marker=dict(size=0.1, opacity=0),
            showlegend=False,
            hoverinfo='text',
            hovertext=f"Task: {row['Name']}<br>Start: {row['Start_Date'].strftime('%Y-%m-%d %H:%M')}<br>Finish: {row['Finish_Date'].strftime('%Y-%m-%d %H:%M')}<br>Duration: {row['Duration']}"
        ))
    
    # Add milestones
    if len(df_milestones) > 0:
        milestone_y_positions = [y_label_to_pos[label] for label in df_milestones['Y_Label']]
        
        fig.add_trace(go.Scatter(
            x=df_milestones['Finish_Date'],
            y=milestone_y_positions,
            mode='markers',
            marker=dict(
                symbol='diamond',
                size=15,
                color='red',
                line=dict(width=1, color='DarkSlateGrey')
            ),
            name='Milestones',
            showlegend=True,
            hoverinfo='text',
            hovertext=df_milestones.apply(
                lambda row: f"Milestone: {row['Name']}<br>Date: {row['Finish_Date'].strftime('%Y-%m-%d %H:%M')}", 
                axis=1
            )
        ))
    
    # Add dependency lines
    for index, row in df_regular.iterrows():
        task_start = row['Start_Date']
        task_y_pos = y_label_to_pos[row['Y_Label']]
        original_predecessors = df.loc[index, 'Parsed_Predecessors']
        
        for pred_idx in original_predecessors:
            predecessor_data = None
            if pred_idx in df_regular.index:
                predecessor_data = df_regular.loc[pred_idx]
            elif pred_idx in df_milestones.index:
                predecessor_data = df_milestones.loc[pred_idx]
            
            if predecessor_data is not None:
                pred_finish = predecessor_data['Finish_Date']
                pred_y_pos = y_label_to_pos[predecessor_data['Y_Label']]
                
                fig.add_trace(go.Scatter(
                    x=[pred_finish, task_start],
                    y=[pred_y_pos, task_y_pos],
                    mode='lines+markers',
                    line=dict(color='grey', width=1, dash='dot'),
                    marker=dict(symbol='arrow', size=10, angleref='previous'),
                    showlegend=False,
                    hoverinfo='text',
                    hovertext=f"Dependency:<br>From: {predecessor_data['Name']}<br>To: {row['Name']}"
                ))
    
    min_date = df['Start_Date'].min()
    max_date = df['Finish_Date'].max()
    
    fig.update_layout(
        shapes=shapes,
        hoverlabel=dict(bgcolor="white", font_size=16, font_family="sans-serif"),
        xaxis_title="Date",
        yaxis_title="Task Name",
        title="Project Gantt Chart with Milestones and Dependencies",
        height=max(600, len(sorted_y_labels) * 25),
        title_x=0.5,
        font=dict(family="Arial, sans-serif", size=12, color="RebeccaPurple"),
        showlegend=True,
        xaxis_type='date',
        xaxis_range=[min_date - pd.Timedelta(days=5), max_date + pd.Timedelta(days=30)],
        xaxis=dict(showgrid=True, gridcolor='LightGray', gridwidth=1),
        yaxis=dict(
            tickmode='array',
            tickvals=list(range(len(sorted_y_labels))),
            ticktext=sorted_y_labels,
            autorange="reversed",
            showgrid=True,
            gridcolor='LightGray',
            gridwidth=1
        ),
        plot_bgcolor='white'
    )
    
    return fig

# Main logic
if uploaded_file is not None:
    try:
        with st.spinner('📊 Gantt chart generálása...'):
            # Read Excel
            df = pd.read_excel(uploaded_file)
            
            # Validate columns
            required_columns = ['Name', 'Start_Date', 'Finish_Date', 'Duration', 
                              'Outline_Level', 'Predecessors', 'Not appear']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                st.error(f"❌ Hiányzó oszlopok: {', '.join(missing_columns)}")
                st.stop()
            
            # Process data
            df, df_regular, df_milestones = process_dataframe(df)
            
            # Create chart
            fig = create_gantt_chart(df, df_regular, df_milestones)
            
            # Success message
            st.success("✅ Gantt Chart sikeresen elkészült!")
            
            # Display stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Összes feladat", len(df_regular))
            with col2:
                st.metric("Mérföldkövek", len(df_milestones))
            with col3:
                project_duration = (df['Finish_Date'].max() - df['Start_Date'].min()).days
                st.metric("Projekt időtartam", f"{project_duration} nap")
            
            # Display chart
            st.plotly_chart(fig, use_container_width=True)
            
            # Download button
            html_bytes = fig.to_html(include_plotlyjs='cdn').encode()
            st.download_button(
                label="💾 Letöltés HTML-ként",
                data=html_bytes,
                file_name="gantt_chart.html",
                mime="text/html"
            )
            
    except Exception as e:
        st.error(f"❌ Hiba történt: {str(e)}")
        with st.expander("🔍 Részletes hibaüzenet"):
            st.exception(e)
else:
    st.info("👆 Kérlek, tölts fel egy Excel fájlt a kezdéshez!")
